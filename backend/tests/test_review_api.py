import os
import httpx
import pytest
from PIL import Image as PILImage
import app.deps as deps
from app.config import Config
from app.db import make_engine, make_session_factory
from app.models import Base, create_all, Image
from app.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://plt:plt@localhost:6666/plt_test")

DATASET = "review-ds"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def env(tmp_path, monkeypatch):
    datasets_root = tmp_path / "datasets"
    ds = datasets_root / DATASET
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir()
    for stem in ("100", "200"):
        PILImage.new("RGB", (640, 640)).save(ds / "images" / f"{stem}.jpg")
        (ds / "labels" / f"{stem}.txt").write_text(
            "0 0.5 0.5 0.1 0.2 " + " ".join("0.4 0.3 2" for _ in range(15)))
    (ds / "model_labeled.txt").write_text("100 0.9 r\n200 0.8 r\n")
    models_root = tmp_path / "models"
    models_root.mkdir()
    cfg = Config(datasets_root=datasets_root, models_root=models_root, db_url=TEST_DB)
    monkeypatch.setattr(deps, "_config", cfg)
    monkeypatch.setattr(deps, "_engine", None)
    monkeypatch.setattr(deps, "_session_factory", None)
    engine = make_engine(TEST_DB)
    Base.metadata.drop_all(engine)
    create_all(deps.get_engine())
    Session = make_session_factory(deps.get_engine())
    s = Session()
    s.add_all([Image(dataset=DATASET, stem="100", in_model_labeled=True, has_label=True),
               Image(dataset=DATASET, stem="200", in_model_labeled=True, has_label=True)])
    s.commit()
    s.close()
    engine.dispose()
    yield ds
    Base.metadata.drop_all(make_engine(TEST_DB))


@pytest.fixture
def client(env):
    app = create_app()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.anyio
async def test_login_creates_user(client):
    async with client as c:
        r = await c.post("/api/login", json={"username": "alice"})
        assert r.status_code == 200
        assert r.json()["username"] == "alice"
        assert isinstance(r.json()["user_id"], int)


@pytest.mark.anyio
async def test_lease_then_submit_autoadvances(client):
    async with client as c:
        uid = (await c.post("/api/login", json={"username": "bob"})).json()["user_id"]
        r = (await c.post("/api/lease", json={
            "dataset": DATASET, "task": "model", "user_id": uid})).json()
        assert r["stem"] == "100"
        assert r["width"] == 640 and len(r["instances"]) == 1
        nxt = (await c.post("/api/submit", json={
            "dataset": DATASET, "stem": "100", "task": "model", "user_id": uid,
            "action": "keep"})).json()
        assert nxt["next"]["stem"] == "200"


@pytest.mark.anyio
async def test_two_users_never_get_same_stem(client):
    async with client as c:
        a = (await c.post("/api/login", json={"username": "a"})).json()["user_id"]
        b = (await c.post("/api/login", json={"username": "b"})).json()["user_id"]
        s1 = (await c.post("/api/lease", json={
            "dataset": DATASET, "task": "all", "user_id": a})).json()["stem"]
        s2 = (await c.post("/api/lease", json={
            "dataset": DATASET, "task": "all", "user_id": b})).json()["stem"]
        assert {s1, s2} == {"100", "200"}


@pytest.mark.anyio
async def test_heartbeat_and_release(client):
    async with client as c:
        uid = (await c.post("/api/login", json={"username": "c"})).json()["user_id"]
        lease_id = (await c.post("/api/lease", json={
            "dataset": DATASET, "task": "all", "user_id": uid})).json()["lease_id"]
        assert (await c.post("/api/heartbeat", json={"lease_id": lease_id})).json()["ok"] is True
        assert (await c.post("/api/release", json={"lease_id": lease_id})).json()["ok"] is True
        assert (await c.post("/api/heartbeat", json={"lease_id": lease_id})).json()["ok"] is False


@pytest.mark.anyio
async def test_lease_is_scoped_to_its_dataset(client, env):
    other = env.parent / "other-ds"
    (other / "images").mkdir(parents=True)
    (other / "labels").mkdir()
    PILImage.new("RGB", (640, 640)).save(other / "images" / "900.jpg")
    async with client as c:
        uid = (await c.post("/api/login", json={"username": "d"})).json()["user_id"]
        r = (await c.post("/api/lease", json={
            "dataset": "other-ds", "task": "all", "user_id": uid})).json()
        assert r["stem"] == "900"


@pytest.mark.anyio
async def test_submit_rejects_an_unknown_dataset(client):
    async with client as c:
        uid = (await c.post("/api/login", json={"username": "e"})).json()["user_id"]
        r = await c.post("/api/submit", json={
            "dataset": "../etc", "stem": "100", "task": "all", "user_id": uid,
            "action": "keep"})
        assert r.status_code == 400


@pytest.mark.anyio
async def test_stats_are_dataset_scoped(client):
    async with client as c:
        r = await c.get("/api/stats", params={"dataset": DATASET, "task": "all"})
        assert r.status_code == 200 and r.json()["total"] == 2
        assert (await c.get("/api/stats", params={"dataset": "nope", "task": "all"})).status_code == 404
