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


@pytest.fixture()
async def client(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    PILImage.new("RGB", (640, 640)).save(tmp_path / "images" / "100.jpg")
    (tmp_path / "labels" / "100.txt").write_text("")
    cfg = Config(dataset_dir=tmp_path, models_dir=tmp_path, db_url=TEST_DB)
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
    r = await client.post("/api/scan")
    assert r.status_code == 200
    assert r.json()["scanned"] == 1
