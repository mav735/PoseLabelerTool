import os
import httpx
import pytest
from PIL import Image as PILImage
import app.deps as deps
from app.config import Config
from app.db import make_engine
from app.models import Base, create_all
from app.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://plt:plt@localhost:6666/plt_test")

DATASET = "serve-ds"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    datasets_root = tmp_path / "datasets"
    ds = datasets_root / DATASET
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir()
    PILImage.new("RGB", (64, 48)).save(ds / "images" / "100.jpg")
    (ds / "labels" / "100.txt").write_text(
        "0 0.5 0.5 0.1 0.2 " + " ".join("0.4 0.3 2" for _ in range(15)))
    models_root = tmp_path / "models"
    models_root.mkdir()
    cfg = Config(datasets_root=datasets_root, models_root=models_root, db_url=TEST_DB)
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None)
    monkeypatch.setattr(deps, "_session_factory", None)
    Base.metadata.drop_all(make_engine(TEST_DB))
    create_all(deps.get_engine())
    app = create_app()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), ds
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.mark.anyio
async def test_get_image_ok_and_traversal_guard(client):
    c, _ = client
    async with c:
        await c.post("/api/scan", params={"dataset": DATASET})
        r = await c.get(f"/api/image/100?dataset={DATASET}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        assert (await c.get(f"/api/image/..%2f..%2fsecret?dataset={DATASET}")).status_code in (400, 404)
        assert (await c.get(f"/api/image/999?dataset={DATASET}")).status_code == 404
        assert (await c.get("/api/image/100?dataset=..%2f..%2fsecret")).status_code == 400


@pytest.mark.anyio
async def test_get_image_underscore_stem(client):
    c, ds = client
    PILImage.new("RGB", (64, 48)).save(ds / "images" / "1_00000297.jpg")
    async with c:
        await c.post("/api/scan", params={"dataset": DATASET})
        r = await c.get(f"/api/image/1_00000297?dataset={DATASET}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


@pytest.mark.anyio
async def test_get_label_payload(client):
    c, _ = client
    async with c:
        await c.post("/api/scan", params={"dataset": DATASET})
        r = (await c.get(f"/api/label/100?dataset={DATASET}")).json()
        assert r["width"] == 64 and r["height"] == 48
        assert len(r["instances"]) == 1
        assert (await c.get("/api/label/100?dataset=nope")).status_code == 404


@pytest.mark.anyio
async def test_trash_restore_purge_cycle(client):
    c, ds = client
    async with c:
        await c.post("/api/scan", params={"dataset": DATASET})
        from app import fswriter
        fswriter.move_to_trash(ds, "", "100")
        assert (await c.get(f"/api/trash?dataset={DATASET}")).json()["stems"] == ["100"]
        assert (await c.post("/api/trash/restore",
                             json={"dataset": DATASET, "stem": "100"})).json()["ok"] is True
        assert (await c.get(f"/api/trash?dataset={DATASET}")).json()["stems"] == []
        fswriter.move_to_trash(ds, "", "100")
        assert (await c.post("/api/trash/purge",
                             json={"dataset": DATASET})).json()["purged"] == 1
        assert (await c.get(f"/api/trash?dataset={DATASET}")).json()["stems"] == []


@pytest.mark.anyio
async def test_trash_is_dataset_scoped(client):
    c, ds = client
    other = ds.parent / "other-ds"
    (other / "images").mkdir(parents=True)
    (other / "labels").mkdir()
    PILImage.new("RGB", (64, 48)).save(other / "images" / "200.jpg")
    async with c:
        from app import fswriter
        fswriter.move_to_trash(other, "", "200")
        assert (await c.get(f"/api/trash?dataset={DATASET}")).json()["stems"] == []
        assert (await c.get("/api/trash?dataset=other-ds")).json()["stems"] == ["200"]
        assert (await c.get("/api/trash?dataset=..%2fetc")).status_code == 400
