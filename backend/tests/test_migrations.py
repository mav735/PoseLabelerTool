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
    command.upgrade(_alembic_cfg(), "head")
    insp = inspect(clean_db)
    for table in Base.metadata.sorted_tables:
        actual = {c["name"]: c["nullable"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            assert col.name in actual, f"{table.name}.{col.name} missing from migration"
            assert actual[col.name] == col.nullable, (
                f"{table.name}.{col.name} nullable={actual[col.name]}, "
                f"ORM says {col.nullable}")


def test_upgrade_works_from_any_cwd(clean_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    command.upgrade(_alembic_cfg(), "head")
    assert "images" in inspect(clean_db).get_table_names()


def test_per_dataset_backfills_existing_rows(clean_db, monkeypatch):
    monkeypatch.setenv("PLT_MIGRATE_DEFAULT_DATASET", "people-v3")
    command.upgrade(_alembic_cfg(), "0001_baseline")
    with clean_db.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (username) VALUES ('alexander')")
        conn.exec_driver_sql(
            "INSERT INTO images (stem, width, height, has_label, "
            "in_model_labeled, in_bad_labels, approved, deleted) VALUES "
            "('100', 0, 0, false, false, false, true, false)")
        conn.exec_driver_sql(
            "INSERT INTO reviews (stem, task, user_id, action) "
            "VALUES ('100', 'all', 1, 'keep')")
    command.upgrade(_alembic_cfg(), "0002_per_dataset")
    with clean_db.begin() as conn:
        assert conn.exec_driver_sql(
            "SELECT dataset FROM images WHERE stem='100'").scalar() == "people-v3"
        assert conn.exec_driver_sql(
            "SELECT dataset FROM reviews WHERE stem='100'").scalar() == "people-v3"
        assert conn.exec_driver_sql(
            "SELECT approved FROM images WHERE stem='100'").scalar() is True


def test_per_dataset_allows_same_stem_in_two_datasets(clean_db):
    command.upgrade(_alembic_cfg(), "head")
    with clean_db.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO images (dataset, stem, width, height, has_label, "
            "in_model_labeled, in_bad_labels, approved, deleted) VALUES "
            "('a', '100', 0, 0, false, false, false, false, false), "
            "('b', '100', 0, 0, false, false, false, false, false)")
        n = conn.exec_driver_sql("SELECT count(*) FROM images").scalar()
    assert n == 2


def test_active_lease_index_is_per_dataset(clean_db):
    command.upgrade(_alembic_cfg(), "head")
    with clean_db.begin() as conn:
        conn.exec_driver_sql("INSERT INTO users (username) VALUES ('u')")
        conn.exec_driver_sql(
            "INSERT INTO leases (dataset, stem, task, user_id, expires_at) "
            "VALUES ('a', '100', 'all', 1, now()), ('b', '100', 'all', 1, now())")
        n = conn.exec_driver_sql("SELECT count(*) FROM leases").scalar()
    assert n == 2


def _reset_deps(monkeypatch):
    import app.deps as deps
    from app.config import Config
    monkeypatch.setattr(deps, "_config", Config(datasets_root=".", models_root=".",
                                                db_url=TEST_DB))
    monkeypatch.setattr(deps, "_engine", None)
    monkeypatch.setattr(deps, "_session_factory", None)


def test_startup_upgrades_an_empty_database(clean_db, monkeypatch):
    from app.main import _migrate_to_head
    _reset_deps(monkeypatch)
    _migrate_to_head()
    insp = inspect(clean_db)
    assert "images" in insp.get_table_names()
    with clean_db.begin() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM alembic_version").scalar() == 1


def test_startup_stamps_a_create_all_database(clean_db, monkeypatch):
    from app.main import _migrate_to_head
    _reset_deps(monkeypatch)
    Base.metadata.create_all(clean_db)
    _migrate_to_head()  # would explode if it tried to upgrade over existing tables
    with clean_db.begin() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM alembic_version").scalar() == 1


def test_startup_is_idempotent_once_stamped(clean_db, monkeypatch):
    from app.main import _migrate_to_head
    _reset_deps(monkeypatch)
    _migrate_to_head()
    _migrate_to_head()
    assert "images" in inspect(clean_db).get_table_names()
