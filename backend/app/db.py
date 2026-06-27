from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_engine(db_url: str):
    return create_engine(db_url, pool_pre_ping=True, future=True)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
