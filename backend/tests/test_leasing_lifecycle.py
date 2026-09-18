import datetime
from app.models import Image, User, Lease
from app.leasing import acquire, heartbeat, release, release_active, sweep_expired

T0 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def _user_image(session):
    u = User(username="u1")
    session.add(u)
    session.add(Image(dataset="ds", stem="100", in_bad_labels=True))
    session.commit()
    return u


def test_heartbeat_extends_expiry(db_session):
    u = _user_image(db_session)
    acquire(db_session, "ds", "bad", u.id, T0, 180)
    lease = db_session.query(Lease).one()
    later = T0 + datetime.timedelta(seconds=60)
    assert heartbeat(db_session, lease.id, later, 180) is True
    db_session.refresh(lease)
    assert lease.expires_at == later + datetime.timedelta(seconds=180)


def test_release_marks_released(db_session):
    u = _user_image(db_session)
    acquire(db_session, "ds", "bad", u.id, T0, 180)
    lease = db_session.query(Lease).one()
    assert release(db_session, lease.id, T0) is True
    db_session.refresh(lease)
    assert lease.released_at is not None
    assert release(db_session, lease.id, T0) is False


def test_release_active_frees_for_reacquire(db_session):
    u = _user_image(db_session)
    assert acquire(db_session, "ds", "bad", u.id, T0, 180) == "100"
    assert acquire(db_session, "ds", "bad", u.id, T0, 180) is None
    assert release_active(db_session, "ds", u.id, "100", "bad", T0) is True
    assert acquire(db_session, "ds", "bad", u.id, T0, 180) == "100"


def test_sweep_expired_releases_stale(db_session):
    u = _user_image(db_session)
    acquire(db_session, "ds", "bad", u.id, T0, 180)
    future = T0 + datetime.timedelta(seconds=200)
    assert sweep_expired(db_session, future) == 1
    assert acquire(db_session, "ds", "bad", u.id, future, 180) == "100"
    assert sweep_expired(db_session, future) == 0
