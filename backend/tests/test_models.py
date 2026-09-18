import datetime
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import User, Image, Lease


def test_user_and_image_roundtrip(db_session):
    db_session.add(User(username="alice"))
    db_session.add(Image(stem="1782200746925", width=640, height=640, has_label=True))
    db_session.commit()
    img = db_session.get(Image, {"dataset": "default", "stem": "1782200746925"})
    assert img.width == 640 and img.has_label is True
    assert img.approved is False and img.deleted is False


def test_partial_unique_lease_blocks_second_active(db_session):
    u = User(username="bob")
    db_session.add(u)
    db_session.commit()
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=180)
    db_session.add(Lease(stem="s1", task="bad", user_id=u.id, expires_at=exp))
    db_session.commit()
    db_session.add(Lease(stem="s1", task="bad", user_id=u.id, expires_at=exp))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_released_lease_allows_reacquire(db_session):
    u = User(username="carol")
    db_session.add(u)
    db_session.commit()
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=180)
    l1 = Lease(stem="s2", task="bad", user_id=u.id, expires_at=exp,
               released_at=datetime.datetime.now(datetime.timezone.utc))
    db_session.add(l1)
    db_session.commit()
    db_session.add(Lease(stem="s2", task="bad", user_id=u.id, expires_at=exp))
    db_session.commit()


def test_active_lease_unique_across_tasks(db_session):
    import datetime
    from app.models import User, Lease
    u = User(username="x")
    db_session.add(u)
    db_session.commit()
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=180)
    db_session.add(Lease(stem="s9", task="bad", user_id=u.id, expires_at=exp))
    db_session.commit()
    db_session.add(Lease(stem="s9", task="all", user_id=u.id, expires_at=exp))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
