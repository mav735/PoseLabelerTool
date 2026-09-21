import os
import httpx
import pytest
from PIL import Image as PILImage
import app.deps as deps
from app.config import Config
from app.db import make_engine
from app.models import Base, create_all, DedupPair, User
from app.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://plt:plt@localhost:6666/plt_test")

DATASET = "dedup-ds"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_ds(root, name, stems):
    ds = root / name
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir()
    for s in stems:
        PILImage.new("RGB", (32, 32)).save(ds / "images" / f"{s}.jpg")
        (ds / "labels" / f"{s}.txt").write_text("")
    return ds


@pytest.fixture
def client(tmp_path, monkeypatch):
    datasets_root = tmp_path / "datasets"
    ds = _make_ds(datasets_root, DATASET, ("100", "200"))
    (ds / "model_labeled.txt").write_text("100 x\n200 x\n")
    models_root = tmp_path / "models"
    models_root.mkdir()
    cfg = Config(datasets_root=datasets_root, models_root=models_root, db_url=TEST_DB)
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None); monkeypatch.setattr(deps, "_session_factory", None)
    Base.metadata.drop_all(make_engine(TEST_DB)); create_all(deps.get_engine())
    s = deps._session_factory()
    s.add(User(username="dedupper"))
    s.add(DedupPair(dataset=DATASET, keeper_stem="100", dup_stem="200", diff=1.0,
                    pool="all", status="todo"))
    s.commit(); s.close()
    app = create_app()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), ds
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.mark.anyio
async def test_dedup_next_then_delete(client):
    c, ds = client
    async with c:
        nxt = (await c.post("/api/dedup/next",
                            json={"dataset": DATASET, "user_id": 1})).json()
        assert nxt["keeper"] == "100" and nxt["dup"] == "200"
        r = (await c.post("/api/dedup/resolve",
                          json={"pair_id": nxt["id"], "action": "delete"})).json()
        assert r["ok"] is True
        assert (ds / ".trash" / "200.jpg").exists()
        assert (await c.post("/api/dedup/next",
                             json={"dataset": DATASET, "user_id": 1})).json()["id"] is None


@pytest.mark.anyio
async def test_dedup_next_scans_so_the_images_serve(client):
    # Setup -> Tools -> dedup review never touches /api/lease or /api/stats,
    # so nothing else on that path creates the Image rows the image endpoints
    # need to resolve a shard. /api/dedup/next has to scan by itself.
    c, _ = client
    async with c:
        nxt = (await c.post("/api/dedup/next",
                            json={"dataset": DATASET, "user_id": 1})).json()
        for stem in (nxt["keeper"], nxt["dup"]):
            r = await c.get(f"/api/image/{stem}", params={"dataset": DATASET})
            assert r.status_code == 200, stem
            assert r.headers["content-type"] == "image/jpeg"
        assert (await c.get(f"/api/label/{nxt['dup']}",
                            params={"dataset": DATASET})).status_code == 200


@pytest.mark.anyio
async def test_dedup_resolve_rejects_bad_action(client):
    c, _ = client
    async with c:
        nxt = (await c.post("/api/dedup/next",
                            json={"dataset": DATASET, "user_id": 1})).json()
        r = await c.post("/api/dedup/resolve", json={"pair_id": nxt["id"], "action": "frobnicate"})
        assert r.status_code == 422


@pytest.mark.anyio
async def test_dedup_resolve_requires_leased(client):
    c, _ = client
    async with c:
        nxt = (await c.post("/api/dedup/next",
                            json={"dataset": DATASET, "user_id": 1})).json()
        await c.post("/api/dedup/resolve", json={"pair_id": nxt["id"], "action": "keep"})
        # already done -> second resolve is 409
        r = await c.post("/api/dedup/resolve", json={"pair_id": nxt["id"], "action": "keep"})
        assert r.status_code == 409


@pytest.mark.anyio
async def test_dedup_next_only_serves_its_own_dataset(client):
    c, ds = client
    other = _make_ds(ds.parent, "other-ds", ("300", "400"))
    s = deps._session_factory()
    s.add(DedupPair(dataset="other-ds", keeper_stem="300", dup_stem="400", diff=2.0,
                    pool="all", status="todo"))
    s.commit(); s.close()
    async with c:
        nxt = (await c.post("/api/dedup/next",
                            json={"dataset": "other-ds", "user_id": 1})).json()
        assert nxt["keeper"] == "300" and nxt["dup"] == "400"
        # resolving takes the dataset from the pair row, not the request
        assert (await c.post("/api/dedup/resolve",
                             json={"pair_id": nxt["id"], "action": "delete"})).json()["ok"] is True
        assert (other / ".trash" / "400.jpg").exists()
        assert not (ds / ".trash").exists()


@pytest.mark.anyio
async def test_dedup_next_rejects_a_bad_dataset(client):
    c, _ = client
    async with c:
        r = await c.post("/api/dedup/next", json={"dataset": "../etc", "user_id": 1})
        assert r.status_code == 400
