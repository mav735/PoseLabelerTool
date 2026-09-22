import datetime
from types import SimpleNamespace
from app.main import due_datasets
from app.models import Job, PendingChange
from app.sync_state import mark_diverged


def _cfg(cat, enabled=True, debounce=60, maxp=50, datasets_root=None):
    return SimpleNamespace(catalog_path=cat, sync_enabled=enabled,
                           sync_debounce_seconds=debounce, sync_max_pending=maxp,
                           datasets_root=datasets_root or cat.parent)


def _cat(tmp_path):
    p = tmp_path / "datasets.yaml"
    p.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    return p


def _add(db_session, n, age_seconds=0):
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(n):
        c = PendingChange(dataset="ds", path=f"labels/{i}.txt", op="add")
        c.created_at = now - datetime.timedelta(seconds=age_seconds)
        db_session.add(c)
    db_session.commit()


def test_a_fresh_small_batch_is_not_due(db_session, tmp_path):
    _add(db_session, 3, age_seconds=0)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert due_datasets(db_session, _cfg(_cat(tmp_path)), now) == []


def test_enough_rows_makes_it_due_immediately(db_session, tmp_path):
    _add(db_session, 50, age_seconds=0)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert due_datasets(db_session, _cfg(_cat(tmp_path)), now) == ["ds"]


def test_an_old_row_makes_it_due_even_if_small(db_session, tmp_path):
    _add(db_session, 1, age_seconds=120)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert due_datasets(db_session, _cfg(_cat(tmp_path)), now) == ["ds"]


def test_nothing_is_due_when_sync_is_disabled(db_session, tmp_path):
    _add(db_session, 100, age_seconds=999)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert due_datasets(db_session, _cfg(_cat(tmp_path), enabled=False), now) == []


def test_a_diverged_dataset_is_never_due(db_session, tmp_path):
    """The spec says auto-sync stops for a diverged dataset -- re-enqueueing a
    job that immediately no-ops would otherwise happen every scheduler tick."""
    _add(db_session, 100, age_seconds=999)
    (tmp_path / "ds").mkdir()
    mark_diverged(tmp_path / "ds")
    now = datetime.datetime.now(datetime.timezone.utc)
    assert due_datasets(db_session, _cfg(_cat(tmp_path)), now) == []


def test_a_recently_created_sync_job_debounces_further_enqueueing(db_session, tmp_path):
    """A persistent failure (401, network outage) must become one attempt per
    debounce window, not one retry every 5-second scheduler tick."""
    _add(db_session, 100, age_seconds=999)
    now = datetime.datetime.now(datetime.timezone.utc)
    job = Job(dataset="ds", type="sync", params={}, status="failed")
    job.created_at = now - datetime.timedelta(seconds=5)
    db_session.add(job)
    db_session.commit()
    assert due_datasets(db_session, _cfg(_cat(tmp_path), debounce=60), now) == []


def test_due_again_once_the_debounce_window_has_passed(db_session, tmp_path):
    _add(db_session, 100, age_seconds=999)
    now = datetime.datetime.now(datetime.timezone.utc)
    job = Job(dataset="ds", type="sync", params={}, status="failed")
    job.created_at = now - datetime.timedelta(seconds=120)
    db_session.add(job)
    db_session.commit()
    assert due_datasets(db_session, _cfg(_cat(tmp_path), debounce=60), now) == ["ds"]
