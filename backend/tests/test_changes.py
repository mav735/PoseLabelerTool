import os
import time

import app.hf.changes as changes
from app.hf.changes import is_repo_content, coalesce, pending_count, record
from app.models import PendingChange


def test_only_images_and_labels_are_repo_content():
    assert is_repo_content("images/003/1.jpg")
    assert is_repo_content("labels/1.txt")
    assert not is_repo_content("reviewed_keep.txt")
    assert not is_repo_content("bad_labels.txt")
    assert not is_repo_content("model_labeled.txt")
    assert not is_repo_content("dataset.yaml")


def test_a_path_that_merely_starts_with_the_word_is_not_content():
    """Prefix matching must be on the directory, not the string."""
    assert not is_repo_content("images_backup/1.jpg")
    assert not is_repo_content("../images/1.jpg")


def test_coalesce_keeps_the_last_op_per_path():
    rows = [PendingChange(dataset="d", path="a.txt", op="add"),
            PendingChange(dataset="d", path="a.txt", op="add"),
            PendingChange(dataset="d", path="b.jpg", op="add"),
            PendingChange(dataset="d", path="b.jpg", op="delete")]
    assert coalesce(rows) == {"a.txt": "add", "b.jpg": "delete"}


def test_coalesce_lets_an_add_follow_a_delete():
    """Trash then restore ends as an add, not a delete."""
    rows = [PendingChange(dataset="d", path="b.jpg", op="delete"),
            PendingChange(dataset="d", path="b.jpg", op="add")]
    assert coalesce(rows) == {"b.jpg": "add"}


def test_record_writes_a_row_for_repo_content(db_session, tmp_path):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    record(lambda: db_session, cat, tmp_path / "ds", "labels/1.txt", "add")
    assert pending_count(db_session, "ds") == 1


def test_record_ignores_bookkeeping(db_session, tmp_path):
    """Filtered at record time: rows that could never be committed would
    inflate the user-visible pending count and churn the table."""
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    record(lambda: db_session, cat, tmp_path / "ds", "reviewed_keep.txt", "add")
    assert pending_count(db_session, "ds") == 0


def test_record_ignores_a_dataset_with_no_repo(db_session, tmp_path):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: ds\nmodels: []\n")
    record(lambda: db_session, cat, tmp_path / "ds", "labels/1.txt", "add")
    assert pending_count(db_session, "ds") == 0


def test_record_ignores_a_dataset_not_in_the_catalog(db_session, tmp_path):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets: []\nmodels: []\n")
    record(lambda: db_session, cat, tmp_path / "ds", "labels/1.txt", "add")
    assert pending_count(db_session, "ds") == 0


def test_record_parses_the_catalog_once_for_two_calls(db_session, tmp_path, monkeypatch):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    real_load = changes.load_catalog_safe
    calls = []
    def counting(path):
        calls.append(path)
        return real_load(path)
    monkeypatch.setattr(changes, "load_catalog_safe", counting)

    record(lambda: db_session, cat, tmp_path / "ds", "labels/1.txt", "add")
    record(lambda: db_session, cat, tmp_path / "ds", "labels/2.txt", "add")

    assert len(calls) == 1
    assert pending_count(db_session, "ds") == 2


def test_record_reparses_after_the_catalog_file_changes(db_session, tmp_path, monkeypatch):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    real_load = changes.load_catalog_safe
    calls = []
    def counting(path):
        calls.append(path)
        return real_load(path)
    monkeypatch.setattr(changes, "load_catalog_safe", counting)

    record(lambda: db_session, cat, tmp_path / "ds", "labels/1.txt", "add")
    # Change the mtime without changing the content -- the cache must key on
    # mtime, not on having seen this exact path before.
    future = time.time() + 5
    os.utime(cat, (future, future))
    record(lambda: db_session, cat, tmp_path / "ds", "labels/2.txt", "add")

    assert len(calls) == 2
