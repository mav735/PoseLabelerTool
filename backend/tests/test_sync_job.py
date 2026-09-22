import pytest
from types import SimpleNamespace
from app.hf.sync import run_sync
from app.hf.fake import FakeHFClient
from app.hf.client import HFConflict
from app.models import Job, PendingChange
from app.sync_state import write_sync, is_diverged, read_sync


def _cfg(root, cat):
    return SimpleNamespace(datasets_root=root, models_root=root / "m",
                           catalog_path=cat, sync_enabled=True)


def _setup(tmp_path, db_session, *, paths=(("labels/003/1.txt", "add"),)):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: ds\n    repo: a/b\n    revision: main\nmodels: []\n")
    d = tmp_path / "ds"
    (d / "labels" / "003").mkdir(parents=True)
    (d / "labels" / "003" / "1.txt").write_text("content")
    write_sync(d, revision="parentsha", completed=True)
    for p, op in paths:
        db_session.add(PendingChange(dataset="ds", path=p, op=op))
    job = Job(dataset="ds", type="sync", params={})
    db_session.add(job); db_session.commit()
    return cat, d, job


def test_sync_commits_adds_and_clears_the_rows(db_session, tmp_path):
    cat, d, job = _setup(tmp_path, db_session)
    client = FakeHFClient()
    run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert client.commits[0]["adds"][0][0] == "labels/003/1.txt"
    assert client.commits[0]["parent_commit"] == "parentsha"
    assert db_session.query(PendingChange).count() == 0


def test_sync_advances_the_marker_to_the_new_sha(db_session, tmp_path):
    """The marker must move to whatever SHA the commit returned.

    Asserted against job.result rather than a literal, so this test does not
    encode FakeHFClient's synthetic-SHA format — which is not the contract and
    would otherwise break this test for an unrelated reason.
    """
    cat, d, job = _setup(tmp_path, db_session)
    run_sync(db_session, _cfg(tmp_path, cat), job, FakeHFClient(sha="newsha"))
    written = read_sync(d)["revision"]
    assert written == job.result["revision"]    # marker matches what was committed
    assert written != "parentsha"               # and genuinely moved off the parent


def test_sync_coalesces_repeated_edits(db_session, tmp_path):
    cat, d, job = _setup(tmp_path, db_session, paths=(
        ("labels/003/1.txt", "add"), ("labels/003/1.txt", "add"),
        ("labels/003/1.txt", "add")))
    client = FakeHFClient()
    run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert len(client.commits[0]["adds"]) == 1


def test_a_conflict_marks_diverged_and_keeps_the_rows(db_session, tmp_path):
    """Losing unpushed work to a conflict would be the worst outcome here."""
    cat, d, job = _setup(tmp_path, db_session)
    client = FakeHFClient(raises=HFConflict("precondition failed"))
    with pytest.raises(HFConflict):
        run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert is_diverged(d) is True
    assert db_session.query(PendingChange).count() == 1


def test_sync_refuses_a_diverged_dataset(db_session, tmp_path):
    cat, d, job = _setup(tmp_path, db_session)
    from app.sync_state import mark_diverged
    mark_diverged(d)
    client = FakeHFClient()
    run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert client.commits == []
    assert db_session.query(PendingChange).count() == 1


def test_a_failed_commit_keeps_the_rows(db_session, tmp_path):
    """Rows are deleted only after success, so a crash replays."""
    from app.hf.client import HFError
    cat, d, job = _setup(tmp_path, db_session)
    client = FakeHFClient(raises=HFError("network went away"))
    with pytest.raises(HFError):
        run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert db_session.query(PendingChange).count() == 1


def test_nothing_pending_is_a_no_op(db_session, tmp_path):
    cat, d, job = _setup(tmp_path, db_session, paths=())
    client = FakeHFClient()
    run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert client.commits == []


def test_an_add_whose_file_vanished_is_skipped(db_session, tmp_path):
    """The file was deleted after the row was written; committing a missing
    local file would fail the whole commit for one stale row."""
    cat, d, job = _setup(tmp_path, db_session,
                         paths=(("labels/003/gone.txt", "add"),))
    client = FakeHFClient()
    run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert client.commits == []
    assert db_session.query(PendingChange).count() == 0


def test_deletes_are_committed(db_session, tmp_path):
    cat, d, job = _setup(tmp_path, db_session,
                         paths=(("images/003/1.jpg", "delete"),))
    client = FakeHFClient()
    run_sync(db_session, _cfg(tmp_path, cat), job, client)
    assert client.commits[0]["deletes"] == ["images/003/1.jpg"]
