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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir(); (tmp_path / "labels").mkdir()
    for s in ("100", "200"):
        PILImage.new("RGB", (32, 32)).save(tmp_path / "images" / f"{s}.jpg")
        (tmp_path / "labels" / f"{s}.txt").write_text("")
    (tmp_path / "model_labeled.txt").write_text("100 x\n200 x\n")
    cfg = Config(dataset_dir=tmp_path, models_dir=tmp_path, db_url=TEST_DB)
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None); monkeypatch.setattr(deps, "_session_factory", None)
    Base.metadata.drop_all(make_engine(TEST_DB)); create_all(deps.get_engine())
    s = deps._session_factory()
    s.add(User(username="dedupper"))
    s.add(DedupPair(keeper_stem="100", dup_stem="200", diff=1.0, pool="all", status="todo"))
    s.commit(); s.close()
    app = create_app()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), tmp_path
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.mark.anyio
async def test_dedup_next_then_delete(client):
    c, root = client
    async with c:
        nxt = (await c.post("/api/dedup/next", json={"user_id": 1})).json()
        assert nxt["keeper"] == "100" and nxt["dup"] == "200"
        r = (await c.post("/api/dedup/resolve", json={"pair_id": nxt["id"], "action": "delete"})).json()
        assert r["ok"] is True
        assert (root / ".trash" / "200.jpg").exists()
        assert (await c.post("/api/dedup/next", json={"user_id": 1})).json()["id"] is None
