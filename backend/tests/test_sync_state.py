from app.sync_state import read_sync, write_sync, is_complete, SYNC_FILE


def test_absent_marker_reads_as_none(tmp_path):
    assert read_sync(tmp_path) is None


def test_a_dataset_with_no_marker_counts_as_complete(tmp_path):
    # A purely local dataset was never downloaded and has no marker.
    # It must stay usable, so absence means complete, not incomplete.
    assert is_complete(tmp_path) is True


def test_write_then_read_round_trip(tmp_path):
    write_sync(tmp_path, revision="abc123", completed=True)
    got = read_sync(tmp_path)
    assert got["revision"] == "abc123"
    assert got["completed"] is True
    assert (tmp_path / SYNC_FILE).exists()


def test_an_incomplete_marker_is_not_complete(tmp_path):
    write_sync(tmp_path, revision="abc123", completed=False)
    assert is_complete(tmp_path) is False


def test_a_complete_marker_is_complete(tmp_path):
    write_sync(tmp_path, revision="abc123", completed=True)
    assert is_complete(tmp_path) is True


def test_a_corrupt_marker_is_not_complete(tmp_path):
    (tmp_path / SYNC_FILE).write_text("{not json")
    assert read_sync(tmp_path) is None
    # A marker we cannot read means we cannot prove the download finished.
    assert is_complete(tmp_path) is False


def test_writing_twice_overwrites(tmp_path):
    write_sync(tmp_path, revision="one", completed=False)
    write_sync(tmp_path, revision="two", completed=True)
    assert read_sync(tmp_path)["revision"] == "two"
