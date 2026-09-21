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

DATASET = "pred-ds"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    datasets_root = tmp_path / "datasets"
    ds = datasets_root / DATASET
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir()
    PILImage.new("RGB", (640, 640)).save(ds / "images" / "100.jpg")
    models_root = tmp_path / "models"
    models_root.mkdir()
    (models_root / "best.pt").write_bytes(b"fake")
    (models_root / "sub").mkdir()
    (models_root / "sub" / "n.pt").write_bytes(b"fake")
    cfg = Config(datasets_root=datasets_root, models_root=models_root, db_url=TEST_DB)
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
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), calls, datasets_root
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.mark.anyio
async def test_models_list(client):
    c, _, _ = client
    async with c:
        r = (await c.get("/api/models")).json()
        paths = sorted(m["path"] for m in r)
        assert paths == ["best.pt", "sub/n.pt"]


@pytest.mark.anyio
async def test_pred_runs_then_caches(client):
    c, calls, _ = client
    async with c:
        await c.post("/api/scan", params={"dataset": DATASET})
        r1 = (await c.get(f"/api/pred/100?dataset={DATASET}&model=best.pt")).json()
        assert len(r1) == 1 and r1[0]["kpts"][0] == [1.0, 2.0, 2]
        r2 = (await c.get(f"/api/pred/100?dataset={DATASET}&model=best.pt")).json()
        assert r2 == r1
        assert calls["n"] == 1   # second call served from cache


@pytest.mark.anyio
async def test_pred_cache_is_per_dataset(client):
    c, calls, datasets_root = client
    other = datasets_root / "other-ds"
    (other / "images").mkdir(parents=True)
    PILImage.new("RGB", (640, 640)).save(other / "images" / "100.jpg")
    async with c:
        await c.post("/api/scan", params={"dataset": DATASET})
        await c.post("/api/scan", params={"dataset": "other-ds"})
        await c.get(f"/api/pred/100?dataset={DATASET}&model=best.pt")
        assert calls["n"] == 1
        # same stem and model, different dataset -> not a cache hit
        await c.get("/api/pred/100?dataset=other-ds&model=best.pt")
        assert calls["n"] == 2


@pytest.mark.anyio
async def test_pred_rejects_bad_stem_and_traversal(client):
    c, _, _ = client
    async with c:
        assert (await c.get(f"/api/pred/abc?dataset={DATASET}&model=best.pt")).status_code == 400
        assert (await c.get(f"/api/pred/100?dataset={DATASET}&model=..%2f..%2fsecret.pt")).status_code == 400
        assert (await c.get("/api/pred/100?dataset=..%2fetc&model=best.pt")).status_code == 400


@pytest.mark.anyio
async def test_jobs_oracle_rejects_traversal_model(client):
    c, _, _ = client
    async with c:
        r = await c.post("/api/jobs", json={"dataset": DATASET, "type": "oracle",
                                            "params": {"model": "..%2f..%2fx.pt"}})
        assert r.status_code == 400
        r2 = await c.post("/api/jobs", json={"dataset": DATASET, "type": "oracle",
                                             "params": {"model": "../../x.pt"}})
        assert r2.status_code == 400


@pytest.mark.anyio
async def test_jobs_record_their_dataset(client):
    c, _, _ = client
    async with c:
        r = await c.post("/api/jobs", json={"dataset": DATASET, "type": "dedup",
                                            "params": {}})
        assert r.status_code == 200
        job_id = r.json()["id"]
        rows = (await c.get("/api/jobs")).json()
        assert [j["dataset"] for j in rows if j["id"] == job_id] == [DATASET]
        bad = await c.post("/api/jobs", json={"dataset": "../etc", "type": "dedup",
                                              "params": {}})
        assert bad.status_code == 400
