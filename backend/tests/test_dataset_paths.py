import pytest
from app.dataset_paths import (safe_shard, image_path, label_path,
                                trash_image_path, trash_label_path,
                                iter_image_files, repo_rel_image, repo_rel_label)


def test_flat_paths_when_shard_is_empty(tmp_path):
    assert image_path(tmp_path, "", "100") == tmp_path / "images" / "100.jpg"
    assert label_path(tmp_path, "", "100") == tmp_path / "labels" / "100.txt"


def test_sharded_paths(tmp_path):
    assert image_path(tmp_path, "003", "100") == tmp_path / "images" / "003" / "100.jpg"
    assert label_path(tmp_path, "003", "100") == tmp_path / "labels" / "003" / "100.txt"


def test_trash_mirrors_the_shard(tmp_path):
    assert trash_image_path(tmp_path, "", "100") == tmp_path / ".trash" / "100.jpg"
    assert trash_image_path(tmp_path, "003", "100") == tmp_path / ".trash" / "003" / "100.jpg"
    assert trash_label_path(tmp_path, "003", "100") == tmp_path / ".trash" / "003" / "100.txt"


@pytest.mark.parametrize("bad", ["../etc", "a/b", "a\\b", ".", "..", "x" * 9, "a b"])
def test_safe_shard_rejects(bad):
    with pytest.raises(ValueError):
        safe_shard(bad)


def test_safe_shard_accepts_empty_and_plain(tmp_path):
    assert safe_shard("") == ""
    assert safe_shard("000") == "000"
    assert safe_shard("shard_1") == "shard_1"


def test_iter_finds_flat_images(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "100.jpg").write_bytes(b"x")
    (tmp_path / "images" / "200.jpg").write_bytes(b"x")
    assert sorted(iter_image_files(tmp_path)) == [("", "100"), ("", "200")]


def test_iter_finds_sharded_images(tmp_path):
    for shard, stem in (("000", "100"), ("000", "101"), ("001", "200")):
        d = tmp_path / "images" / shard
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{stem}.jpg").write_bytes(b"x")
    assert sorted(iter_image_files(tmp_path)) == [("000", "100"), ("000", "101"), ("001", "200")]


def test_iter_finds_both_shapes_together(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "flat.jpg").write_bytes(b"x")
    (tmp_path / "images" / "000").mkdir()
    (tmp_path / "images" / "000" / "100.jpg").write_bytes(b"x")
    assert sorted(iter_image_files(tmp_path)) == [("", "flat"), ("000", "100")]


def test_iter_ignores_a_second_nesting_level(tmp_path):
    deep = tmp_path / "images" / "000" / "deeper"
    deep.mkdir(parents=True)
    (deep / "100.jpg").write_bytes(b"x")
    assert list(iter_image_files(tmp_path)) == []


def test_iter_missing_images_dir_is_empty(tmp_path):
    assert list(iter_image_files(tmp_path)) == []


def test_iter_tolerates_an_empty_shard_dir(tmp_path):
    (tmp_path / "images" / "000").mkdir(parents=True)
    (tmp_path / "images" / "001").mkdir()
    (tmp_path / "images" / "001" / "100.jpg").write_bytes(b"x")
    assert list(iter_image_files(tmp_path)) == [("001", "100")]


def test_iter_skips_a_shard_dir_with_an_unsafe_name(tmp_path):
    d = tmp_path / "images" / "way-too-long-name"
    d.mkdir(parents=True)
    (d / "100.jpg").write_bytes(b"x")
    assert list(iter_image_files(tmp_path)) == []


def test_sharded_repo_paths():
    assert repo_rel_image("003", "100") == "images/003/100.jpg"
    assert repo_rel_label("003", "100") == "labels/003/100.txt"


def test_flat_repo_paths():
    """shard == "" means flat, exactly as it does on disk."""
    assert repo_rel_image("", "100") == "images/100.jpg"
    assert repo_rel_label("", "100") == "labels/100.txt"


def test_repo_paths_reject_a_bad_shard():
    with pytest.raises(ValueError):
        repo_rel_image("../etc", "100")


def test_repo_paths_always_use_forward_slashes():
    """These are repo keys, not filesystem paths — never os.sep."""
    assert "\\" not in repo_rel_image("003", "100")
