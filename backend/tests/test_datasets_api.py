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


@pytest.mark.anyio
async def test_lists_disk_and_catalog_datasets(client, datasets_root):
    (datasets_root / "on-disk" / "images").mkdir(parents=True)
    rows = (await client.get("/api/datasets")).json()
    names = [r["name"] for r in rows]
    assert "on-disk" in names
    row = next(r for r in rows if r["name"] == "on-disk")
    assert row["ready"] is True
    assert row["repo"] is None


@pytest.mark.anyio
async def test_add_dataset_appends_to_catalog(client):
    r = await client.post("/api/datasets", json={"name": "hands-v1", "repo": "mav735/hands"})
    assert r.status_code == 200
    rows = (await client.get("/api/datasets")).json()
    row = next(r for r in rows if r["name"] == "hands-v1")
    assert row["repo"] == "mav735/hands"
    assert row["local"] is False
    assert row["ready"] is False


@pytest.mark.anyio
async def test_add_duplicate_dataset_is_rejected(client):
    await client.post("/api/datasets", json={"name": "hands-v1"})
    r = await client.post("/api/datasets", json={"name": "hands-v1"})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_get_unknown_dataset_is_404(client):
    r = await client.get("/api/datasets/nope")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_add_dataset_rejects_bad_name(client):
    r = await client.post("/api/datasets", json={"name": "../etc"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_get_known_dataset_by_name(client, datasets_root):
    (datasets_root / "on-disk" / "images").mkdir(parents=True)
    r = await client.get("/api/datasets/on-disk")
    assert r.status_code == 200
    assert r.json()["name"] == "on-disk"


@pytest.mark.anyio
async def test_malformed_catalog_still_lists_local_datasets(client, datasets_root):
    (datasets_root / "on-disk" / "images").mkdir(parents=True)
    cfg = deps.get_config()
    cfg.catalog_path.write_text("datasets: [oops\n")
    r = await client.get("/api/datasets")
    assert r.status_code == 200
    rows = r.json()
    names = [row["name"] for row in rows]
    assert "on-disk" in names
    row = next(row for row in rows if row["name"] == "on-disk")
    assert row["catalog_error"] is not None
