import os
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect
from app.db import make_engine
from app.models import Base

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://plt:plt@localhost:6666/plt_test")


def _alembic_cfg():
    cfg = AlembicConfig(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    return cfg


@pytest.fixture()
def clean_db():
    engine = make_engine(TEST_DB)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    yield engine
    engine.dispose()


def test_baseline_creates_core_tables(clean_db):
    command.upgrade(_alembic_cfg(), "0001_baseline")
    names = set(inspect(clean_db).get_table_names())
    assert {"users", "images", "leases", "reviews",
            "dedup_pairs", "jobs", "pred_cache"} <= names


def test_baseline_matches_orm_metadata(clean_db):
    command.upgrade(_alembic_cfg(), "0001_baseline")
    insp = inspect(clean_db)
    for table in Base.metadata.sorted_tables:
        actual = {c["name"]: c["nullable"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            assert col.name in actual, f"{table.name}.{col.name} missing from migration"
            assert actual[col.name] == col.nullable, (
                f"{table.name}.{col.name} nullable={actual[col.name]}, "
                f"ORM says {col.nullable}")
