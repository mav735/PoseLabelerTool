import os
import httpx
import pytest
from PIL import Image as PILImage
import app.deps as deps
import app.inference as inference
from app.config import Config
from app.db import make_engine
from app.models import Base, create_all
from app.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://plt:plt@localhost:6666/plt_test")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    (tmp_path / "models").mkdir()
    PILImage.new("RGB", (640, 640)).save(tmp_path / "images" / "100.jpg")
    (tmp_path / "models" / "best.pt").write_bytes(b"fake")
    (tmp_path / "models" / "sub").mkdir()
    (tmp_path / "models" / "sub" / "n.pt").write_bytes(b"fake")
    cfg = Config(dataset_dir=tmp_path, models_dir=tmp_path / "models", db_url=TEST_DB)
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None)
    monkeypatch.setattr(deps, "_session_factory", None)
    Base.metadata.drop_all(make_engine(TEST_DB))
    create_all(deps.get_engine())
    calls = {"n": 0}
    monkeypatch.setattr(inference, "load_model", lambda p: object())
    def fake_run(model, source, conf=0.15, iou_thr=0.45):
        calls["n"] += 1
        return [((0, 0, 5, 5), 0.9, [[1.0, 2.0, 0.9]] + [[0.0, 0.0, 0.0]] * 14)]
    monkeypatch.setattr(inference, "run_pred", fake_run)
    app = create_app()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), calls
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.mark.anyio
async def test_models_list(client):
    c, _ = client
    async with c:
        r = (await c.get("/api/models")).json()
        paths = sorted(m["path"] for m in r)
        assert paths == ["best.pt", "sub/n.pt"]


@pytest.mark.anyio
async def test_pred_runs_then_caches(client):
    c, calls = client
    async with c:
        r1 = (await c.get("/api/pred/100?model=best.pt")).json()
        assert len(r1) == 1 and r1[0]["kpts"][0] == [1.0, 2.0, 2]
        r2 = (await c.get("/api/pred/100?model=best.pt")).json()
        assert r2 == r1
        assert calls["n"] == 1   # second call served from cache


@pytest.mark.anyio
async def test_pred_rejects_bad_stem_and_traversal(client):
    c, _ = client
    async with c:
        assert (await c.get("/api/pred/abc?model=best.pt")).status_code == 400
        assert (await c.get("/api/pred/100?model=..%2f..%2fsecret.pt")).status_code == 400


@pytest.mark.anyio
async def test_jobs_oracle_rejects_traversal_model(client):
    c, _ = client
    async with c:
        r = await c.post("/api/jobs", json={"type": "oracle", "params": {"model": "..%2f..%2fx.pt"}})
        assert r.status_code == 400
        r2 = await c.post("/api/jobs", json={"type": "oracle", "params": {"model": "../../x.pt"}})
        assert r2.status_code == 400
