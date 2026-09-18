import os
import threading
from pathlib import Path
from PIL import Image as PILImage
from app.db import make_engine, make_session_factory
from app.models import Image
from app.main import _ensure_scanned

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://plt:plt@localhost:6666/plt_test")


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


def test_a_second_scan_of_the_same_dataset_is_a_no_op(db_session, tmp_path):
    """Calling twice must not raise and must not duplicate rows."""
    ds_dir = _ds(tmp_path / "alpha")
    _ensure_scanned(db_session, "alpha", ds_dir)
    _ensure_scanned(db_session, "alpha", ds_dir)
    assert db_session.query(Image).filter(Image.dataset == "alpha").count() == 1


def test_concurrent_first_scans_do_not_collide(db_session, tmp_path):
    """Three real sessions racing a first scan: one scans, the rest see rows.

    This is the /api/stats race -- TaskStep fires three stats requests at once
    and FastAPI runs the non-async endpoint on a threadpool, so all three reach
    _ensure_scanned on independent sessions before any of them has committed.
    Without serialisation the losers raise UniqueViolation on the images pkey.
    """
    ds_dir = _ds(tmp_path / "gamma")
    engine = make_engine(TEST_DB)
    Session = make_session_factory(engine)
    n = 3
    start = threading.Barrier(n)
    errors: list[BaseException] = []

    def worker():
        session = Session()
        try:
            start.wait(timeout=30)
            _ensure_scanned(session, "gamma", ds_dir)
        except BaseException as exc:      # noqa: BLE001 - recorded, re-raised below
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "a scan thread deadlocked"
    engine.dispose()
    assert errors == [], f"concurrent scans raised: {errors!r}"

    db_session.rollback()   # fresh snapshot of what the threads committed
    rows = db_session.query(Image).filter(Image.dataset == "gamma").all()
    assert [r.stem for r in rows] == ["100"]
