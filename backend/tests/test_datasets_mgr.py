import pytest
from app.catalog import Catalog, DatasetEntry
from app.datasets_mgr import (safe_dataset_path, is_ready, dir_size,
                               discover, list_status)


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
