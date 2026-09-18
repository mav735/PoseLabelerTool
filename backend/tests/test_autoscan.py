from pathlib import Path
from PIL import Image as PILImage
from app.models import Image
from app.main import _ensure_scanned


def _ds(root: Path) -> Path:
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    PILImage.new("RGB", (64, 64)).save(root / "images" / "100.jpg")
    (root / "labels" / "100.txt").write_text("")
    return root


def test_scans_on_first_use(db_session, tmp_path):
    ds_dir = _ds(tmp_path / "alpha")
    _ensure_scanned(db_session, "alpha", ds_dir)
    assert db_session.get(Image, ("alpha", "100")) is not None


def test_skips_a_dataset_already_populated(db_session, tmp_path):
    ds_dir = _ds(tmp_path / "alpha")
    db_session.add(Image(dataset="alpha", stem="999"))
    db_session.commit()
    _ensure_scanned(db_session, "alpha", ds_dir)
    assert db_session.get(Image, ("alpha", "100")) is None


def test_another_dataset_being_populated_does_not_block_the_scan(db_session, tmp_path):
    ds_dir = _ds(tmp_path / "beta")
    db_session.add(Image(dataset="alpha", stem="999"))
    db_session.commit()
    _ensure_scanned(db_session, "beta", ds_dir)
    assert db_session.get(Image, ("beta", "100")) is not None
