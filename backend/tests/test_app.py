import os
import httpx
import pytest
from PIL import Image as PILImage
import app.deps as deps
from app.config import Config
from app.db import make_engine
from app.models import Base, create_all, Image
from app.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://plt:plt@localhost:6666/plt_test")

DATASET = "ds1"


def _write_jpg(path, size=(640, 640)):
    PILImage.new("RGB", size).save(path)


@pytest.fixture()
def datasets_root(tmp_path):
    root = tmp_path / "datasets"
    root.mkdir()
    return root


@pytest.fixture()
async def client(tmp_path, datasets_root, monkeypatch):
    ds = datasets_root / DATASET
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir()
    _write_jpg(ds / "images" / "100.jpg")
    (ds / "labels" / "100.txt").write_text("")
    models_root = tmp_path / "models"
    models_root.mkdir()
    cfg = Config(datasets_root=datasets_root, models_root=models_root, db_url=TEST_DB)
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
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_scan_endpoint(client):
    r = await client.post("/api/scan", params={"dataset": DATASET})
    assert r.status_code == 200
    assert r.json()["scanned"] == 1


@pytest.mark.anyio
async def test_lease_requires_a_known_dataset(client):
    r = await client.post("/api/lease",
                          json={"dataset": "../etc", "task": "all", "user_id": 1})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_lease_rejects_an_invalid_task(client):
    # task_filter raises ValueError for anything outside leasing.TASKS, and
    # nothing used to map that to a client error -- it reached the handler
    # as a 500. The Literal on LeaseReq.task makes FastAPI reject it first.
    r = await client.post("/api/lease",
                          json={"dataset": DATASET, "task": "approve", "user_id": 1})
    assert 400 <= r.status_code < 500


@pytest.mark.anyio
async def test_image_endpoint_is_dataset_scoped(client):
    r = await client.get("/api/image/100", params={"dataset": "nope"})
    assert r.status_code in (400, 404)


@pytest.mark.anyio
async def test_scan_endpoint_rejects_unknown_dataset(client):
    r = await client.post("/api/scan", params={"dataset": "nope"})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_first_lease_scans_the_dataset(client, db_session, datasets_root):
    d = datasets_root / "fresh"
    (d / "images").mkdir(parents=True)
    (d / "labels").mkdir()
    _write_jpg(d / "images" / "100.jpg")
    uid = (await client.post("/api/login", json={"username": "scanner"})).json()["user_id"]
    assert db_session.query(Image).filter(Image.dataset == "fresh").count() == 0
    r = await client.post("/api/lease",
                          json={"dataset": "fresh", "task": "all", "user_id": uid})
    assert r.status_code == 200
    assert r.json()["stem"] == "100"
    assert db_session.query(Image).filter(Image.dataset == "fresh").count() == 1
