import datetime
import pytest
from app.leasing import task_stats
from app.models import Image, Lease, User


def test_task_stats_counts(db_session):
    """task_stats returns correct total/done/leased/todo breakdown."""
    user = User(username="stats_tester")
    db_session.add(user)
    db_session.flush()

    now = datetime.datetime.now(datetime.timezone.utc)

    # img1: done (approved)
    db_session.add(Image(dataset="ds", stem="s001", in_model_labeled=True, approved=True, deleted=False))
    # img2: active lease → leased
    db_session.add(Image(dataset="ds", stem="s002", in_model_labeled=True, approved=False, deleted=False))
    # img3: no lease, not approved → todo
    db_session.add(Image(dataset="ds", stem="s003", in_model_labeled=True, approved=False, deleted=False))
    # img4: deleted → excluded
    db_session.add(Image(dataset="ds", stem="s004", in_model_labeled=True, approved=False, deleted=True))
    # img5: not in task filter (in_model_labeled=False) → excluded
    db_session.add(Image(dataset="ds", stem="s005", in_model_labeled=False, approved=False, deleted=False))
    db_session.flush()

    db_session.add(Lease(
        dataset="ds", stem="s002", task="model", user_id=user.id,
        expires_at=now + datetime.timedelta(seconds=30),
    ))
    db_session.commit()

    result = task_stats(db_session, "ds", "model")

    assert result["total"] == 3
    assert result["done"] == 1
    assert result["leased"] == 1
    assert result["todo"] == 1
    assert result["total"] == result["done"] + result["leased"] + result["todo"]


def test_task_stats_all_task(db_session):
    """'all' task counts every non-deleted image."""
    db_session.add(Image(dataset="ds", stem="a001", in_model_labeled=False, in_bad_labels=False, approved=False, deleted=False))
    db_session.add(Image(dataset="ds", stem="a002", in_model_labeled=False, in_bad_labels=False, approved=True,  deleted=False))
    db_session.add(Image(dataset="ds", stem="a003", in_model_labeled=False, in_bad_labels=False, approved=False, deleted=True))
    db_session.commit()

    result = task_stats(db_session, "ds", "all")

    assert result["total"] == 2
    assert result["done"] == 1
    assert result["leased"] == 0
    assert result["todo"] == 1
