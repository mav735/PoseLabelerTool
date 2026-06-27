import datetime
from sqlalchemy import select, exists, true
from app.models import Image, Lease

TASKS = ("bad", "model", "all")


def task_filter(task: str):
    if task == "bad":
        return Image.in_bad_labels.is_(True)
    if task == "model":
        return Image.in_model_labeled.is_(True)
    if task == "all":
        return true()
    raise ValueError(f"unknown task: {task}")


def acquire(session, task: str, user_id: int, now: datetime.datetime,
            lease_timeout: int):
    active = exists(select(Lease.id).where(
        Lease.stem == Image.stem, Lease.released_at.is_(None)))
    stmt = (select(Image.stem)
            .where(Image.deleted.is_(False), Image.approved.is_(False),
                   task_filter(task), ~active)
            .order_by(Image.stem)
            .with_for_update(skip_locked=True)
            .limit(1))
    stem = session.execute(stmt).scalar_one_or_none()
    if stem is None:
        session.rollback()
        return None
    session.add(Lease(stem=stem, task=task, user_id=user_id,
                      expires_at=now + datetime.timedelta(seconds=lease_timeout)))
    session.commit()
    return stem
