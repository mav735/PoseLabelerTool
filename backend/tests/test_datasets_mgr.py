import tempfile
from pathlib import Path

import pytest
from app.catalog import Catalog, DatasetEntry
from app.datasets_mgr import (safe_dataset_path, is_ready, dir_size,
                               discover, list_status)
from app.sync_state import write_sync


def _fs_is_case_insensitive() -> bool:
    """Probe tempfile.gettempdir(), not the OS name.

    This is not necessarily the filesystem pytest's tmp_path lives on --
    they coincide under default pytest config, but diverge under a custom
    --basetemp.

    macOS APFS is case-insensitive (so 'People-V3' and 'people-v3' are one
    directory) while ext4 is case-sensitive (so they are two). The behaviour
    of safe_dataset_path is correct on both; only the expectations differ.
    """
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "CaseProbe").mkdir()
        return (Path(d) / "caseprobe").exists()


CASE_INSENSITIVE_FS = _fs_is_case_insensitive()

needs_case_insensitive_fs = pytest.mark.skipif(
    not CASE_INSENSITIVE_FS,
    reason="needs a case-insensitive filesystem (e.g. APFS/NTFS); on a "
           "case-sensitive one the two spellings are genuinely two directories")

needs_case_sensitive_fs = pytest.mark.skipif(
    CASE_INSENSITIVE_FS,
    reason="needs a case-sensitive filesystem (e.g. ext4/XFS); on a "
           "case-insensitive one the two spellings collide into one directory")


@pytest.mark.parametrize("bad", ["", "..", "../etc", "a/b", "a\\b", ".hidden", "/abs"])
def test_safe_dataset_path_rejects(tmp_path, bad):
    with pytest.raises(ValueError):
        safe_dataset_path(tmp_path, bad)


def test_safe_dataset_path_accepts_plain_name(tmp_path):
    assert safe_dataset_path(tmp_path, "people-v3") == (tmp_path / "people-v3").resolve()


def test_is_ready_requires_images_dir(tmp_path):
    d = tmp_path / "ds"
    d.mkdir()
    assert is_ready(d) is False
    (d / "images").mkdir()
    assert is_ready(d) is True


def test_dir_size_sums_files(tmp_path):
    d = tmp_path / "ds"
    (d / "images").mkdir(parents=True)
    (d / "images" / "1.jpg").write_bytes(b"x" * 10)
    (d / "labels.txt").write_bytes(b"y" * 5)
    assert dir_size(d) == 15


def test_discover_finds_dirs_with_images(tmp_path):
    (tmp_path / "people-v3" / "images").mkdir(parents=True)
    (tmp_path / "hands-v1" / "images").mkdir(parents=True)
    (tmp_path / "not-a-dataset").mkdir()
    assert discover(tmp_path) == ["hands-v1", "people-v3"]


def test_discover_missing_root_is_empty(tmp_path):
    assert discover(tmp_path / "nope") == []


def test_list_status_unions_catalog_and_disk(tmp_path):
    (tmp_path / "on-disk" / "images").mkdir(parents=True)
    (tmp_path / "on-disk" / "images" / "1.jpg").write_bytes(b"x" * 4)
    cat = Catalog(datasets=[DatasetEntry(name="remote-only", repo="a/b")])
    rows = list_status(tmp_path, cat)
    by_name = {r["name"]: r for r in rows}
    assert by_name["on-disk"]["local"] is True
    assert by_name["on-disk"]["ready"] is True
    assert by_name["on-disk"]["size_bytes"] == 4
    assert by_name["on-disk"]["repo"] is None
    assert by_name["remote-only"]["local"] is False
    assert by_name["remote-only"]["ready"] is False
    assert by_name["remote-only"]["repo"] == "a/b"


@needs_case_insensitive_fs
def test_safe_dataset_path_rejects_case_mismatch(tmp_path):
    """Dataset directory created as 'people-v3' rejects request for 'People-V3'."""
    (tmp_path / "people-v3" / "images").mkdir(parents=True)
    with pytest.raises(ValueError, match="case does not match"):
        safe_dataset_path(tmp_path, "People-V3")


def test_safe_dataset_path_accepts_matching_case(tmp_path):
    """Dataset directory with matching case resolves fine."""
    (tmp_path / "people-v3" / "images").mkdir(parents=True)
    assert safe_dataset_path(tmp_path, "people-v3") == (tmp_path / "people-v3").resolve()


def test_safe_dataset_path_allows_nonexistent_name(tmp_path):
    """Non-existent dataset name still resolves to a path (for local: False case)."""
    # No directory created; this is a catalog entry that hasn't been downloaded
    assert safe_dataset_path(tmp_path, "absent-dataset") == (tmp_path / "absent-dataset").resolve()


@needs_case_insensitive_fs
def test_list_status_skips_case_mismatched_catalog_entry(tmp_path):
    """list_status with catalog 'People-V3' and disk 'people-v3' returns ONE row."""
    (tmp_path / "people-v3" / "images").mkdir(parents=True)
    (tmp_path / "people-v3" / "images" / "1.jpg").write_bytes(b"x" * 4)
    # Catalog entry with mismatched case
    cat = Catalog(datasets=[DatasetEntry(name="People-V3", repo="a/b")])
    rows = list_status(tmp_path, cat)
    # Should have exactly one row: the on-disk one
    assert len(rows) == 1
    assert rows[0]["name"] == "people-v3"
    assert rows[0]["local"] is True
    assert rows[0]["ready"] is True


@needs_case_sensitive_fs
def test_safe_dataset_path_accepts_both_spellings_when_fs_is_case_sensitive(tmp_path):
    """On ext4 'People-V3' and 'people-v3' are two independent datasets."""
    (tmp_path / "people-v3" / "images").mkdir(parents=True)
    (tmp_path / "People-V3" / "images").mkdir(parents=True)
    assert safe_dataset_path(tmp_path, "people-v3") == (tmp_path / "people-v3").resolve()
    assert safe_dataset_path(tmp_path, "People-V3") == (tmp_path / "People-V3").resolve()


@needs_case_sensitive_fs
def test_list_status_lists_both_spellings_when_fs_is_case_sensitive(tmp_path):
    """Two directories differing only in case are two rows, not one."""
    (tmp_path / "people-v3" / "images").mkdir(parents=True)
    (tmp_path / "people-v3" / "images" / "1.jpg").write_bytes(b"x" * 4)
    (tmp_path / "People-V3" / "images").mkdir(parents=True)
    (tmp_path / "People-V3" / "images" / "1.jpg").write_bytes(b"x" * 7)
    cat = Catalog(datasets=[DatasetEntry(name="People-V3", repo="a/b")])
    rows = list_status(tmp_path, cat)
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"people-v3", "People-V3"}
    assert by_name["people-v3"]["ready"] is True
    assert by_name["people-v3"]["size_bytes"] == 4
    assert by_name["people-v3"]["repo"] is None
    assert by_name["People-V3"]["ready"] is True
    assert by_name["People-V3"]["size_bytes"] == 7
    assert by_name["People-V3"]["repo"] == "a/b"


def test_a_half_downloaded_dataset_is_not_ready(tmp_path):
    d = tmp_path / "half"
    (d / "images").mkdir(parents=True)
    write_sync(d, revision="abc", completed=False)
    assert is_ready(d) is False


def test_a_completed_download_is_ready(tmp_path):
    d = tmp_path / "done"
    (d / "images").mkdir(parents=True)
    write_sync(d, revision="abc", completed=True)
    assert is_ready(d) is True


def test_a_local_dataset_with_no_marker_stays_ready(tmp_path):
    d = tmp_path / "local"
    (d / "images").mkdir(parents=True)
    assert is_ready(d) is True


def test_auth_required_when_a_repo_entry_has_no_token(tmp_path):
    cat = Catalog(datasets=[DatasetEntry(name="remote", repo="a/b")])
    row = list_status(tmp_path, cat, token_present=False)[0]
    assert row["auth_required"] is True


def test_auth_not_required_with_a_token(tmp_path):
    cat = Catalog(datasets=[DatasetEntry(name="remote", repo="a/b")])
    row = list_status(tmp_path, cat, token_present=True)[0]
    assert row["auth_required"] is False


def test_a_local_only_dataset_never_requires_auth(tmp_path):
    (tmp_path / "onlylocal" / "images").mkdir(parents=True)
    row = [r for r in list_status(tmp_path, Catalog(), token_present=False)
           if r["name"] == "onlylocal"][0]
    assert row["auth_required"] is False


def test_sync_complete_is_false_for_a_half_downloaded_dataset(tmp_path):
    d = tmp_path / "half"
    (d / "images").mkdir(parents=True)
    write_sync(d, revision="abc", completed=False)
    row = [r for r in list_status(tmp_path, Catalog()) if r["name"] == "half"][0]
    assert row["sync_complete"] is False
    assert row["local"] is True          # the trap: local is true, so the UI
    assert row["ready"] is False         # must not gate a retry on `local`


def test_sync_complete_is_true_for_a_plain_local_dataset(tmp_path):
    (tmp_path / "plain" / "images").mkdir(parents=True)
    row = [r for r in list_status(tmp_path, Catalog()) if r["name"] == "plain"][0]
    assert row["sync_complete"] is True


def test_sync_complete_is_true_for_a_dataset_not_on_disk(tmp_path):
    cat = Catalog(datasets=[DatasetEntry(name="remote", repo="a/b")])
    row = [r for r in list_status(tmp_path, cat) if r["name"] == "remote"][0]
    assert row["local"] is False
    assert row["sync_complete"] is True
