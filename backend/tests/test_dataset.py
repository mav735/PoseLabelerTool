from pathlib import Path
from PIL import Image as PILImage
from app.dataset import (read_stem_list, append_line, prune_stems, image_dims, scan)
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
    counts = scan(db_session, tmp_path)
    assert counts["scanned"] == 2
    i100 = db_session.get(Image, "100")
    assert i100.width == 640 and i100.has_label is True
    assert i100.in_model_labeled is True and i100.approved is False
    i200 = db_session.get(Image, "200")
    assert i200.has_label is False and i200.approved is True


def test_scan_marks_missing_deleted(db_session, tmp_path):
    _make_dataset(tmp_path)
    scan(db_session, tmp_path)
    (tmp_path / "images" / "100.jpg").unlink()
    scan(db_session, tmp_path)
    assert db_session.get(Image, "100").deleted is True
