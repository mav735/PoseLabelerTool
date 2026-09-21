from PIL import Image as PILImage
from app.models import Image, User
from app.dataset import scan
from app import actions, leasing
import datetime


def _sharded_dataset(root):
    for shard, stems in (("000", ["100", "101"]), ("003", ["300"])):
        (root / "images" / shard).mkdir(parents=True)
        (root / "labels" / shard).mkdir(parents=True)
        for s in stems:
            PILImage.new("RGB", (64, 64)).save(root / "images" / shard / f"{s}.jpg")
            (root / "labels" / shard / f"{s}.txt").write_text("")
    return root


def test_sharded_dataset_scan_lease_edit_drop_restore(db_session, tmp_path):
    ds = _sharded_dataset(tmp_path)
    db_session.add(User(id=1, username="u"))
    db_session.commit()

    counts = scan(db_session, "rust", ds)
    assert counts["scanned"] == 3

    now = datetime.datetime.now(datetime.timezone.utc)
    stem = leasing.acquire(db_session, "rust", "all", 1, now, 180)
    assert stem is not None
    shard = db_session.get(Image, ("rust", stem)).shard
    assert shard in ("000", "003")

    # edit writes into the shard, not the root
    actions.apply_action(db_session, "rust", ds, stem, "all", 1, "clear")
    assert (ds / "labels" / shard / f"{stem}.txt").exists()
    assert not (ds / "labels" / f"{stem}.txt").exists()

    # drop moves into a mirrored trash, restore puts it back in the same shard
    actions.apply_action(db_session, "rust", ds, "300", "all", 1, "drop")
    assert (ds / ".trash" / "003" / "300.jpg").exists()
    assert not (ds / "images" / "003" / "300.jpg").exists()

    from app import fswriter
    assert fswriter.restore_from_trash(ds, "003", "300") is True
    assert (ds / "images" / "003" / "300.jpg").exists()
