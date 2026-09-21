from pathlib import Path
from PIL import Image as PILImage
from app.dataset import (read_stem_list, append_line, prune_stems, image_dims, scan, image_stems)
from app.models import Image


def _make_dataset(root: Path):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    for stem, w, h, label in [
        ("100", 640, 640, "0 0.5 0.5 0.1 0.2 " + " ".join("0.4 0.3 2" for _ in range(15))),
        ("200", 320, 240, ""),
    ]:
        PILImage.new("RGB", (w, h)).save(root / "images" / f"{stem}.jpg")
        (root / "labels" / f"{stem}.txt").write_text(label)
    (root / "model_labeled.txt").write_text("100 0.9 reason\n")
    (root / "reviewed_keep.txt").write_text("200\n")


def test_read_stem_list(tmp_path):
    p = tmp_path / "l.txt"
    p.write_text("100 0.9 foo\n200\n\n")
    assert read_stem_list(p) == {"100", "200"}


def test_append_line_dedups(tmp_path):
    p = tmp_path / "k.txt"
    append_line(p, "100")
    append_line(p, "100")
    append_line(p, "200")
    assert p.read_text() == "100\n200\n"


def test_prune_stems(tmp_path):
    p = tmp_path / "m.txt"
    p.write_text("100 a\n200 b\n300 c\n")
    prune_stems(p, {"200"})
    assert p.read_text() == "100 a\n300 c\n"


def test_image_dims(tmp_path):
    f = tmp_path / "x.jpg"
    PILImage.new("RGB", (123, 45)).save(f)
    assert image_dims(f) == (123, 45)


def test_scan_reconciles(db_session, tmp_path):
    _make_dataset(tmp_path)
    counts = scan(db_session, "ds", tmp_path)
    assert counts["scanned"] == 2
    i100 = db_session.get(Image, ("ds", "100"))
    assert i100.width == 640 and i100.has_label is True
    assert i100.in_model_labeled is True and i100.approved is False
    i200 = db_session.get(Image, ("ds", "200"))
    assert i200.has_label is False and i200.approved is True


def test_scan_marks_missing_deleted(db_session, tmp_path):
    _make_dataset(tmp_path)
    scan(db_session, "ds", tmp_path)
    (tmp_path / "images" / "100.jpg").unlink()
    scan(db_session, "ds", tmp_path)
    assert db_session.get(Image, ("ds", "100")).deleted is True


def test_scan_is_scoped_to_dataset(db_session, tmp_path):
    for name in ("a", "b"):
        d = tmp_path / name
        (d / "images").mkdir(parents=True)
        (d / "labels").mkdir()
        PILImage.new("RGB", (10, 10)).save(d / "images" / "100.jpg")
    scan(db_session, "a", tmp_path / "a")
    scan(db_session, "b", tmp_path / "b")
    rows = db_session.query(Image).order_by(Image.dataset).all()
    assert [(r.dataset, r.stem) for r in rows] == [("a", "100"), ("b", "100")]


def test_scan_only_marks_its_own_dataset_deleted(db_session, tmp_path):
    (tmp_path / "a" / "images").mkdir(parents=True)
    (tmp_path / "a" / "labels").mkdir()
    db_session.add(Image(dataset="b", stem="999", deleted=False))
    db_session.commit()
    scan(db_session, "a", tmp_path / "a")
    other = db_session.get(Image, ("b", "999"))
    assert other.deleted is False


def _make_sharded(root, shard, stems):
    img = root / "images" / shard
    lbl = root / "labels" / shard
    img.mkdir(parents=True, exist_ok=True)
    lbl.mkdir(parents=True, exist_ok=True)
    for s in stems:
        PILImage.new("RGB", (32, 32)).save(img / f"{s}.jpg")
        (lbl / f"{s}.txt").write_text("")


def test_scan_records_shards(db_session, tmp_path):
    _make_sharded(tmp_path, "000", ["100", "101"])
    _make_sharded(tmp_path, "003", ["300"])
    scan(db_session, "ds", tmp_path)
    rows = {r.stem: r.shard for r in db_session.query(Image).all()}
    assert rows == {"100": "000", "101": "000", "300": "003"}


def test_scan_of_a_flat_dataset_leaves_shard_empty(db_session, tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    PILImage.new("RGB", (32, 32)).save(tmp_path / "images" / "100.jpg")
    scan(db_session, "ds", tmp_path)
    assert db_session.get(Image, ("ds", "100")).shard == ""


def test_image_stems_finds_sharded_images(tmp_path):
    _make_sharded(tmp_path, "000", ["200", "100"])
    assert image_stems(tmp_path) == ["100", "200"]


def test_scan_updates_the_shard_when_a_file_moves(db_session, tmp_path):
    _make_sharded(tmp_path, "000", ["100"])
    scan(db_session, "ds", tmp_path)
    assert db_session.get(Image, ("ds", "100")).shard == "000"
    # move it to another shard, as a re-download with a changed layout would
    (tmp_path / "images" / "001").mkdir(parents=True)
    (tmp_path / "images" / "000" / "100.jpg").rename(tmp_path / "images" / "001" / "100.jpg")
    scan(db_session, "ds", tmp_path)
    assert db_session.get(Image, ("ds", "100")).shard == "001"
