import datetime
import pytest
from app.models import Image, User, Lease
from app.leasing import acquire, task_filter

NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def _seed(session):
    u = User(username="u1")
    session.add(u)
    session.add_all([
        Image(stem="100", in_bad_labels=True, in_model_labeled=True),
        Image(stem="200", in_model_labeled=True),
        Image(stem="300", approved=True, in_bad_labels=True),
        Image(stem="400", deleted=True, in_bad_labels=True),
    ])
    session.commit()
    return u


def test_task_filter_unknown_raises():
    with pytest.raises(ValueError):
        task_filter("nope")


def test_acquire_bad_returns_lowest_eligible(db_session):
    u = _seed(db_session)
    stem = acquire(db_session, "bad", u.id, NOW, 180)
    assert stem == "100"
    lease = db_session.query(Lease).filter_by(stem="100").one()
    assert lease.released_at is None
    assert lease.task == "bad"


def test_acquire_excludes_approved_and_deleted(db_session):
    u = _seed(db_session)
    got = []
    while True:
        s = acquire(db_session, "bad", u.id, NOW, 180)
        if s is None:
            break
        got.append(s)
    assert got == ["100"]  # 300 approved, 400 deleted excluded; 200 not in bad


def test_acquire_excludes_globally_leased_across_tasks(db_session):
    u = _seed(db_session)
    first = acquire(db_session, "all", u.id, NOW, 180)
    assert first == "100"
    second = acquire(db_session, "bad", u.id, NOW, 180)
    assert second is None  # 100 already leased under "all" → excluded from "bad" too


def test_acquire_empty_pool_returns_none(db_session):
    u = _seed(db_session)
    assert acquire(db_session, "all", u.id, NOW, 180) == "100"
    assert acquire(db_session, "all", u.id, NOW, 180) == "200"
    assert acquire(db_session, "all", u.id, NOW, 180) is None
