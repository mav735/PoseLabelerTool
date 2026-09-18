import datetime
from sqlalchemy import (String, Integer, Float, Boolean, DateTime, Text,
                        ForeignKey, Index, func, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Image(Base):
    __tablename__ = "images"
    dataset: Mapped[str] = mapped_column(String(64), primary_key=True)
    stem: Mapped[str] = mapped_column(String(32), primary_key=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    has_label: Mapped[bool] = mapped_column(Boolean, default=False)
    in_model_labeled: Mapped[bool] = mapped_column(Boolean, default=False)
    in_bad_labels: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class Lease(Base):
    __tablename__ = "leases"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(64))
    stem: Mapped[str] = mapped_column(String(32))
    task: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    leased_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("uq_active_lease_stem", "dataset", "stem", unique=True,
              postgresql_where=text("released_at IS NULL")),
    )


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(64), index=True)
    stem: Mapped[str] = mapped_column(String(32), index=True)
    task: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DedupPair(Base):
    __tablename__ = "dedup_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(64), index=True)
    keeper_stem: Mapped[str] = mapped_column(String(32))
    dup_stem: Mapped[str] = mapped_column(String(32), index=True)
    diff: Mapped[float] = mapped_column(Float)
    pool: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(8), default="todo")
    action: Mapped[str | None] = mapped_column(String(8), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(8), default="queued")
    processed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class PredCache(Base):
    __tablename__ = "pred_cache"
    dataset: Mapped[str] = mapped_column(String(64), primary_key=True)
    stem: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    preds: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def create_all(engine):
    Base.metadata.create_all(engine)
