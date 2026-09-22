import datetime
from types import SimpleNamespace
from app.main import due_datasets
from app.models import PendingChange


def _cfg(cat, enabled=True, debounce=60, maxp=50):
    return SimpleNamespace(catalog_path=cat, sync_enabled=enabled,
                           sync_debounce_seconds=debounce, sync_max_pending=maxp)


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
