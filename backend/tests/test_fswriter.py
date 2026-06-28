import pytest
from pathlib import Path
from PIL import Image as PILImage
from app import fswriter


def _ds(root: Path):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    PILImage.new("RGB", (640, 640)).save(root / "images" / "100.jpg")
    (root / "labels" / "100.txt").write_text("0 0.5 0.5 0.1 0.2\n")
    (root / "model_labeled.txt").write_text("100 0.9 r\n200 0.8 r\n")
    (root / "bad_labels.txt").write_text("100 0.7 r\n")
    return root


def test_write_and_clear_label(tmp_path):
    _ds(tmp_path)
    fswriter.write_label(tmp_path, "100", "0 0.1 0.1 0.2 0.2\n")
    assert (tmp_path / "labels" / "100.txt").read_text() == "0 0.1 0.1 0.2 0.2\n"
    fswriter.clear_label(tmp_path, "100")
    assert (tmp_path / "labels" / "100.txt").read_text() == ""


def test_append_keep_dedups(tmp_path):
    _ds(tmp_path)
    fswriter.append_keep(tmp_path, "100")
    fswriter.append_keep(tmp_path, "100")
    assert (tmp_path / "reviewed_keep.txt").read_text() == "100\n"


def test_prune_from_lists(tmp_path):
    _ds(tmp_path)
    fswriter.prune_from_lists(tmp_path, "100")
    assert (tmp_path / "model_labeled.txt").read_text() == "200 0.8 r\n"
    assert (tmp_path / "bad_labels.txt").read_text() == ""


def test_move_to_trash_and_restore(tmp_path):
    _ds(tmp_path)
    fswriter.move_to_trash(tmp_path, "100")
    assert not (tmp_path / "images" / "100.jpg").exists()
    assert not (tmp_path / "labels" / "100.txt").exists()
    assert (tmp_path / ".trash" / "100.jpg").exists()
    assert (tmp_path / ".trash" / "100.txt").exists()
    assert fswriter.list_trash(tmp_path) == ["100"]
    assert fswriter.restore_from_trash(tmp_path, "100") is True
    assert (tmp_path / "images" / "100.jpg").exists()
    assert (tmp_path / "labels" / "100.txt").exists()
    assert fswriter.list_trash(tmp_path) == []


def test_restore_missing_returns_false(tmp_path):
    _ds(tmp_path)
    assert fswriter.restore_from_trash(tmp_path, "999") is False


def test_purge_one_and_all(tmp_path):
    _ds(tmp_path)
    PILImage.new("RGB", (10, 10)).save(tmp_path / "images" / "200.jpg")
    (tmp_path / "labels" / "200.txt").write_text("x")
    fswriter.move_to_trash(tmp_path, "100")
    fswriter.move_to_trash(tmp_path, "200")
    assert fswriter.purge_trash(tmp_path, "100") == 1
    assert not (tmp_path / ".trash" / "100.jpg").exists()
    assert fswriter.list_trash(tmp_path) == ["200"]
    assert fswriter.purge_trash(tmp_path) == 1
    assert fswriter.list_trash(tmp_path) == []


def test_accepts_underscore_stem(tmp_path):
    _ds(tmp_path)
    PILImage.new("RGB", (640, 640)).save(tmp_path / "images" / "1_00000297.jpg")
    (tmp_path / "labels" / "1_00000297.txt").write_text("0 0.5 0.5 0.1 0.2\n")
    fswriter.move_to_trash(tmp_path, "1_00000297")
    assert (tmp_path / ".trash" / "1_00000297.jpg").exists()
    assert fswriter.restore_from_trash(tmp_path, "1_00000297") is True
    assert (tmp_path / "images" / "1_00000297.jpg").exists()


def test_rejects_path_traversal_stem(tmp_path):
    _ds(tmp_path)
    for bad in ("../evil", "..\\evil", "a/b", "100;rm", "..", ""):
        with pytest.raises(ValueError):
            fswriter.write_label(tmp_path, bad, "x")
        with pytest.raises(ValueError):
            fswriter.move_to_trash(tmp_path, bad)
        with pytest.raises(ValueError):
            fswriter.restore_from_trash(tmp_path, bad)
        with pytest.raises(ValueError):
            fswriter.purge_trash(tmp_path, bad)
    assert fswriter.purge_trash(tmp_path) == 0  # purge-all (stem=None) still works
