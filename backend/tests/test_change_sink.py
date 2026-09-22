import pytest
from app import fswriter


@pytest.fixture()
def sink():
    calls = []
    fswriter.set_change_sink(lambda dd, path, op: calls.append((path, op)))
    yield calls
    fswriter.set_change_sink(None)          # always restore, even on failure


def _ds(tmp_path):
    (tmp_path / "images" / "003").mkdir(parents=True)
    (tmp_path / "labels" / "003").mkdir(parents=True)
    return tmp_path


def test_write_label_records_an_add(tmp_path, sink):
    fswriter.write_label(_ds(tmp_path), "003", "100", "x")
    assert sink == [("labels/003/100.txt", "add")]


def test_clear_label_records_an_add(tmp_path, sink):
    """An emptied label is content, not an absence."""
    fswriter.clear_label(_ds(tmp_path), "003", "100")
    assert sink == [("labels/003/100.txt", "add")]


def test_a_flat_dataset_records_flat_paths(tmp_path, sink):
    (tmp_path / "labels").mkdir(parents=True)
    fswriter.write_label(tmp_path, "", "100", "x")
    assert sink == [("labels/100.txt", "add")]


def test_trashing_records_two_deletes(tmp_path, sink):
    d = _ds(tmp_path)
    (d / "images" / "003" / "100.jpg").write_bytes(b"x")
    (d / "labels" / "003" / "100.txt").write_text("y")
    fswriter.move_to_trash(d, "003", "100")
    assert set(sink) == {("images/003/100.jpg", "delete"),
                         ("labels/003/100.txt", "delete")}


def test_trashing_an_unlabelled_image_records_only_the_image(tmp_path, sink):
    """`moved` (the return value) is computed from the image alone, but the
    label is only moved `if src.exists()`. Recording a label delete here would
    queue a delete for a path that exists neither locally nor in the repo --
    which fails the ENTIRE HuggingFace commit and replays forever.

    Equality, not membership: a membership assertion would pass even if a
    spurious label delete were also recorded, which is exactly the bug.
    """
    d = _ds(tmp_path)
    (d / "images" / "003" / "100.jpg").write_bytes(b"x")   # image only, no label
    fswriter.move_to_trash(d, "003", "100")
    assert sink == [("images/003/100.jpg", "delete")]


def test_a_trash_miss_records_nothing(tmp_path, sink):
    """move_to_trash returns False when the file was not where the shard said.

    Recording a delete then would commit a removal for a path we never had —
    the remote equivalent of reporting a deletion that did not happen.
    """
    assert fswriter.move_to_trash(_ds(tmp_path), "003", "100") is False
    assert sink == []


def test_restore_records_adds(tmp_path, sink):
    d = _ds(tmp_path)
    (d / "images" / "003" / "100.jpg").write_bytes(b"x")
    (d / "labels" / "003" / "100.txt").write_text("y")
    fswriter.move_to_trash(d, "003", "100")
    sink.clear()
    fswriter.restore_from_trash(d, "003", "100")
    assert set(sink) == {("images/003/100.jpg", "add"),
                         ("labels/003/100.txt", "add")}


def test_restoring_an_image_with_no_label_records_only_the_image(tmp_path, sink):
    """restore_from_trash moves the label only if one was trashed.

    Recording both unconditionally would queue a pending change for a file that
    does not exist — dropped later at sync time, but only after inflating the
    unsynced count the user sees.
    """
    d = _ds(tmp_path)
    (d / "images" / "003" / "100.jpg").write_bytes(b"x")   # image only, no label
    fswriter.move_to_trash(d, "003", "100")
    sink.clear()
    fswriter.restore_from_trash(d, "003", "100")
    assert sink == [("images/003/100.jpg", "add")]


def test_purging_records_nothing(tmp_path, sink):
    """Trashing already recorded the delete; purging is local housekeeping."""
    d = _ds(tmp_path)
    (d / "images" / "003" / "100.jpg").write_bytes(b"x")
    fswriter.move_to_trash(d, "003", "100")
    sink.clear()
    fswriter.purge_trash(d, shard="003", stem="100")
    assert sink == []


def test_bookkeeping_files_are_reported_by_their_own_name(tmp_path, sink):
    """fswriter reports everything; the RECORDER decides what is repo content."""
    fswriter.append_keep(tmp_path, "100")
    assert sink == [("reviewed_keep.txt", "add")]


def test_no_sink_is_the_default(tmp_path):
    fswriter.set_change_sink(None)
    fswriter.write_label(_ds(tmp_path), "003", "100", "x")   # must not raise
