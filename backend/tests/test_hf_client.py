import pytest
from app.hf.client import token_from_env, HFError, HFAuthError
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
