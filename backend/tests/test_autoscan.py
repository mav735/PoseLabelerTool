from pathlib import Path
from PIL import Image as PILImage
from app.models import Image
from app.main import maybe_initial_scan
from app.config import Config


def _ds(root: Path):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    PILImage.new("RGB", (64, 64)).save(root / "images" / "100.jpg")
    (root / "labels" / "100.txt").write_text("")
    return root


def test_initial_scan_runs_when_empty(db_session, tmp_path):
    _ds(tmp_path)
    cfg = Config(dataset_dir=tmp_path, models_dir=tmp_path, db_url="x")
    n = maybe_initial_scan(db_session, cfg)
    assert n == 1
    assert db_session.get(Image, "100") is not None


def test_initial_scan_skips_when_populated(db_session, tmp_path):
    _ds(tmp_path)
    db_session.add(Image(stem="999"))
    db_session.commit()
    cfg = Config(dataset_dir=tmp_path, models_dir=tmp_path, db_url="x")
    assert maybe_initial_scan(db_session, cfg) == 0
