import os
import httpx
import pytest
import app.deps as deps
from app.config import Config
from app.db import make_engine
from app.models import Base, create_all
from app.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://plt:plt@localhost:6666/plt_test")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def datasets_root(tmp_path):
    root = tmp_path / "datasets"
    root.mkdir()
    return root


@pytest.fixture()
async def client(tmp_path, datasets_root, monkeypatch):
    models_root = tmp_path / "models"
    models_root.mkdir()
    cfg = Config(datasets_root=datasets_root, models_root=models_root, db_url=TEST_DB,
                catalog_path=tmp_path / "datasets.yaml")
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None)
    monkeypatch.setattr(deps, "_session_factory", None)
    Base.metadata.drop_all(make_engine(TEST_DB))
    create_all(deps.get_engine())
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.fixture()
def catalog_path(tmp_path):
    return tmp_path / "datasets.yaml"


@pytest.mark.anyio
async def test_sync_queues_a_job(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    r = await client.post("/api/datasets/ds/sync")
    assert r.status_code == 200
    assert isinstance(r.json()["job_id"], int)


@pytest.mark.anyio
async def test_sync_rejects_a_local_only_dataset(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: ds\nmodels: []\n")
    assert (await client.post("/api/datasets/ds/sync")).status_code == 400


@pytest.mark.anyio
async def test_a_second_sync_is_rejected(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    assert (await client.post("/api/datasets/ds/sync")).status_code == 200
    assert (await client.post("/api/datasets/ds/sync")).status_code == 409


@pytest.mark.anyio
async def test_pending_preview_lists_paths_and_ages(client, catalog_path, datasets_root):
    catalog_path.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    (datasets_root / "ds" / "labels").mkdir(parents=True)
    from app.hf import changes
    import app.deps as deps
    changes.record(deps._session_factory, catalog_path,
                   datasets_root / "ds", "labels/1.txt", "add")
    body = (await client.get("/api/datasets/ds/pending")).json()
    assert body["count"] == 1
    assert body["changes"][0]["path"] == "labels/1.txt"
    assert body["changes"][0]["op"] == "add"
    assert "age_seconds" in body["changes"][0]


@pytest.mark.anyio
async def test_dataset_rows_carry_pending_and_diverged(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: ds\n    repo: a/b\nmodels: []\n")
    row = [r for r in (await client.get("/api/datasets")).json() if r["name"] == "ds"][0]
    assert row["pending_changes"] == 0
    assert row["diverged"] is False
