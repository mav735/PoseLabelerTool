from pathlib import Path
import pytest
from PIL import Image as PILImage
from app.models import Image, User, Review
from app.actions import apply_action, instances_to_text


def _ds(root: Path):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    for stem in ("100",):
        PILImage.new("RGB", (640, 640)).save(root / "images" / f"{stem}.jpg")
        (root / "labels" / f"{stem}.txt").write_text("0 0.5 0.5 0.1 0.2\n")
    (root / "model_labeled.txt").write_text("100 0.9 r\n")
    return root


def _seed(session, dataset="a"):
    u = User(username="u1")
    session.add(u)
    session.add(Image(dataset=dataset, stem="100", in_model_labeled=True, has_label=True))
    session.commit()
    return u


def test_instances_to_text_refits_box_and_drops_empty():
    insts = [
        {"kpts": [[100.0, 50.0, 2]] + [[0.0, 0.0, 0]] * 13 + [[200.0, 150.0, 2]]},
        {"kpts": [[0.0, 0.0, 0]] * 15},
    ]
    text = instances_to_text(insts, 640, 640)
    lines = text.strip().split("\n")
    assert len(lines) == 1
    p = lines[0].split()
    assert p[0] == "0"
    assert p[3] == "0.162500" and p[4] == "0.162500"  # bw=(202-98)/640=0.1625, bh=(152-48)/640


def test_keep_appends_reviewed_keep_and_approves(db_session, tmp_path):
    u = _seed(db_session)
    _ds(tmp_path)
    apply_action(db_session, "a", tmp_path, "100", "model", u.id, "keep")
    assert (tmp_path / "reviewed_keep.txt").read_text() == "100\n"
    assert db_session.get(Image, ("a", "100")).approved is True
    assert db_session.query(Review).filter_by(action="keep").count() == 1


def test_clear_writes_empty_label(db_session, tmp_path):
    u = _seed(db_session)
    _ds(tmp_path)
    apply_action(db_session, "a", tmp_path, "100", "model", u.id, "clear")
    assert (tmp_path / "labels" / "100.txt").read_text() == ""
    img = db_session.get(Image, ("a", "100"))
    assert img.approved is True and img.has_label is False


def test_drop_moves_to_trash_and_prunes(db_session, tmp_path):
    u = _seed(db_session)
    _ds(tmp_path)
    apply_action(db_session, "a", tmp_path, "100", "model", u.id, "drop")
    assert not (tmp_path / "images" / "100.jpg").exists()
    assert (tmp_path / ".trash" / "100.jpg").exists()
    assert (tmp_path / "model_labeled.txt").read_text() == ""
    img = db_session.get(Image, ("a", "100"))
    assert img.deleted is True and img.approved is False


def test_replace_writes_label_from_kpts(db_session, tmp_path):
    u = _seed(db_session)
    _ds(tmp_path)
    insts = [{"kpts": [[100.0, 50.0, 2]] + [[0.0, 0.0, 0]] * 13 + [[200.0, 150.0, 2]]}]
    apply_action(db_session, "a", tmp_path, "100", "model", u.id, "replace",
                 instances=insts, width=640, height=640)
    text = (tmp_path / "labels" / "100.txt").read_text()
    assert text.startswith("0 ")
    img = db_session.get(Image, ("a", "100"))
    assert img.approved is True and img.has_label is True
    assert db_session.query(Review).filter_by(action="replace").count() == 1


def test_unknown_action_raises(db_session, tmp_path):
    u = _seed(db_session)
    _ds(tmp_path)
    with pytest.raises(ValueError):
        apply_action(db_session, "a", tmp_path, "100", "model", u.id, "frobnicate")


def test_replace_derives_dims_when_omitted(db_session, tmp_path):
    u = _seed(db_session)
    _ds(tmp_path)  # creates images/100.jpg at 640x640
    insts = [{"kpts": [[100.0, 50.0, 2]] + [[0.0, 0.0, 0]] * 13 + [[200.0, 150.0, 2]]}]
    apply_action(db_session, "a", tmp_path, "100", "model", u.id, "replace",
                 instances=insts, width=None, height=None)
    text = (tmp_path / "labels" / "100.txt").read_text()
    assert text.startswith("0 ")  # dims filled from the 640x640 image, no crash


def test_edit_writes_into_the_shard(db_session, tmp_path):
    (tmp_path / "labels" / "003").mkdir(parents=True)
    db_session.add_all([
        Image(dataset="a", stem="100", shard="003", width=100, height=100),
        User(id=1, username="u"),
    ])
    db_session.commit()
    apply_action(db_session, "a", tmp_path, "100", "all", 1, "clear")
    assert (tmp_path / "labels" / "003" / "100.txt").read_text() == ""
    assert not (tmp_path / "labels" / "100.txt").exists()


def test_keep_only_touches_its_own_dataset(db_session, tmp_path):
    (tmp_path / "labels").mkdir(parents=True)
    db_session.add_all([
        Image(dataset="a", stem="100"),
        Image(dataset="b", stem="100"),
        User(id=1, username="u"),
    ])
    db_session.commit()
    apply_action(db_session, "a", tmp_path, "100", "all", 1, "keep")
    assert db_session.get(Image, ("a", "100")).approved is True
    assert db_session.get(Image, ("b", "100")).approved is False
    review = db_session.query(Review).one()
    assert review.dataset == "a"
