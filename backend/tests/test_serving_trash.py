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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    PILImage.new("RGB", (64, 48)).save(tmp_path / "images" / "100.jpg")
    (tmp_path / "labels" / "100.txt").write_text(
        "0 0.5 0.5 0.1 0.2 " + " ".join("0.4 0.3 2" for _ in range(15)))
    cfg = Config(dataset_dir=tmp_path, models_dir=tmp_path, db_url=TEST_DB)
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None)
    monkeypatch.setattr(deps, "_session_factory", None)
    Base.metadata.drop_all(make_engine(TEST_DB))
    create_all(deps.get_engine())
    app = create_app()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), tmp_path
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.mark.anyio
async def test_get_image_ok_and_traversal_guard(client):
    c, _ = client
    async with c:
        r = await c.get("/api/image/100")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        assert (await c.get("/api/image/..%2f..%2fsecret")).status_code in (400, 404)
        assert (await c.get("/api/image/999")).status_code == 404


@pytest.mark.anyio
async def test_get_image_underscore_stem(client):
    c, root = client
    PILImage.new("RGB", (64, 48)).save(root / "images" / "1_00000297.jpg")
    async with c:
        r = await c.get("/api/image/1_00000297")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


@pytest.mark.anyio
async def test_get_label_payload(client):
    c, _ = client
    async with c:
        r = (await c.get("/api/label/100")).json()
        assert r["width"] == 64 and r["height"] == 48
        assert len(r["instances"]) == 1


@pytest.mark.anyio
async def test_trash_restore_purge_cycle(client):
    c, root = client
    async with c:
        from app import fswriter
        fswriter.move_to_trash(root, "100")
        assert (await c.get("/api/trash")).json()["stems"] == ["100"]
        assert (await c.post("/api/trash/restore", json={"stem": "100"})).json()["ok"] is True
        assert (await c.get("/api/trash")).json()["stems"] == []
        fswriter.move_to_trash(root, "100")
        assert (await c.post("/api/trash/purge", json={})).json()["purged"] == 1
        assert (await c.get("/api/trash")).json()["stems"] == []
