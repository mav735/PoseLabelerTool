import datetime
from sqlalchemy import select, exists, func, true
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


def heartbeat(session, lease_id: int, now: datetime.datetime, lease_timeout: int) -> bool:
    lease = session.get(Lease, lease_id)
    if lease is None or lease.released_at is not None:
        return False
    lease.heartbeat_at = now
    lease.expires_at = now + datetime.timedelta(seconds=lease_timeout)
    session.commit()
    return True


def release(session, lease_id: int, now: datetime.datetime) -> bool:
    lease = session.get(Lease, lease_id)
    if lease is None or lease.released_at is not None:
        return False
    lease.released_at = now
    session.commit()
    return True


def release_active(session, user_id: int, stem: str, task: str,
                   now: datetime.datetime) -> bool:
    stmt = select(Lease).where(
        Lease.user_id == user_id, Lease.stem == stem, Lease.task == task,
        Lease.released_at.is_(None))
    lease = session.execute(stmt).scalars().first()
    if lease is None:
        return False
    lease.released_at = now
    session.commit()
    return True


def task_stats(session, task: str) -> dict:
    base = [Image.deleted.is_(False), task_filter(task)]
    total = session.scalar(select(func.count()).select_from(Image).where(*base))
    done = session.scalar(
        select(func.count()).select_from(Image).where(*base, Image.approved.is_(True)))
    active_lease = exists(select(Lease.id).where(
        Lease.stem == Image.stem, Lease.released_at.is_(None)))
    leased = session.scalar(
        select(func.count()).select_from(Image).where(
            *base, Image.approved.is_(False), active_lease))
    todo = total - done - leased
    return {"total": total, "done": done, "leased": leased, "todo": todo}


def sweep_expired(session, now: datetime.datetime) -> int:
    stmt = select(Lease).where(Lease.released_at.is_(None), Lease.expires_at < now)
    leases = session.execute(stmt).scalars().all()
    for lease in leases:
        lease.released_at = now
    session.commit()
    return len(leases)
