import io

import pytest
from app.hf.client import _progress_class, token_from_env, HFError, HFAuthError
from app.hf.fake import FakeHFClient


def test_token_from_env_reads_plt_hf_token(monkeypatch):
    monkeypatch.setenv("PLT_HF_TOKEN", "hf_example")
    assert token_from_env() == "hf_example"


def test_token_from_env_is_none_when_unset(monkeypatch):
    monkeypatch.delenv("PLT_HF_TOKEN", raising=False)
    assert token_from_env() is None


def test_fake_reports_size_and_sha():
    c = FakeHFClient(size=1234, sha="deadbeef")
    assert c.repo_size("a/b") == 1234
    assert c.repo_sha("a/b") == "deadbeef"


def test_fake_snapshot_writes_files_and_reports_bytes(tmp_path):
    c = FakeHFClient(files={"images/000/1.jpg": b"xxxx", "labels/000/1.txt": b"y"})
    seen = []
    c.snapshot("a/b", "main", tmp_path, on_bytes=seen.append)
    assert (tmp_path / "images" / "000" / "1.jpg").read_bytes() == b"xxxx"
    assert (tmp_path / "labels" / "000" / "1.txt").read_bytes() == b"y"
    assert sum(seen) == 5


def test_fake_snapshot_reports_file_counts(tmp_path):
    c = FakeHFClient(files={"a.txt": b"x", "b.txt": b"y", "c.txt": b"z"})
    files = []
    c.snapshot("a/b", "main", tmp_path, on_files=lambda n, total: files.append((n, total)))
    assert sum(n for n, _ in files) == 3
    assert files[0][1] == 3


def test_fake_file_size_is_the_one_file_not_the_repo():
    c = FakeHFClient(files={"small.pt": b"xx", "huge.pt": b"x" * 100})
    assert c.repo_size("a/m") == 102
    assert c.file_size("a/m", "small.pt") == 2


def test_fake_can_raise_auth():
    c = FakeHFClient(raises=HFAuthError("not authorised for a/b"))
    with pytest.raises(HFAuthError):
        c.repo_size("a/b")


def test_fake_can_fail_partway_through(tmp_path):
    c = FakeHFClient(files={"a.txt": b"aa", "b.txt": b"bb"}, fail_after_bytes=2)
    seen = []
    with pytest.raises(HFError):
        c.snapshot("a/b", "main", tmp_path, on_bytes=seen.append)
    assert sum(seen) == 2          # progress reported up to the failure


def test_fake_has_token_reflects_construction():
    assert FakeHFClient(has_token=False).has_token is False
    assert FakeHFClient().has_token is True


def test_progress_class_reports_furthest_bar_not_the_sum_of_both():
    # huggingface_hub 1.x builds TWO unit="B" bars for one snapshot download
    # (network bytes, then bytes reconstructed to disk). Both call update().
    # They measure the same transfer, so summing their deltas double-counts
    # it; the honest total is whichever bar is furthest along.
    #
    # tqdm's __init__ short-circuits when disable=True and never sets `unit`
    # at all (verified: hasattr(bar, "unit") is False), so bars here are
    # built with file=io.StringIO() instead, which does set `unit` normally.
    byte_events = []
    file_events = []
    cls = _progress_class(on_bytes=byte_events.append,
                          on_files=lambda n, total: file_events.append((n, total)))

    network_bar = cls(total=16, unit="B", file=io.StringIO())
    disk_bar = cls(total=16, unit="B", file=io.StringIO())

    network_bar.update(5)   # network: 5   -> forwarded max delta: 5
    disk_bar.update(6)      # disk:    6   -> forwarded max delta: 1  (6-5)
    network_bar.update(3)   # network: 8   -> forwarded max delta: 2  (8-6)
    disk_bar.update(10)     # disk:    16  -> forwarded max delta: 8  (16-8)

    assert sum(byte_events) == 16          # max(8, 16), not the sum (24)

    files_bar = cls(total=3)  # no unit="B" -> routed to on_files, not on_bytes
    files_bar.update(1)
    assert file_events == [(1, 3)]
    assert sum(byte_events) == 16          # unchanged by the file-count bar
