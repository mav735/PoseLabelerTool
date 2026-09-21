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


@pytest.fixture()
def catalog_path(tmp_path):
    return tmp_path / "datasets.yaml"


@pytest.mark.anyio
async def test_download_queues_a_job(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: rust\n    repo: a/b\n    revision: main\nmodels: []\n")
    r = await client.post("/api/datasets/rust/download")
    assert r.status_code == 200
    assert isinstance(r.json()["job_id"], int)


@pytest.mark.anyio
async def test_download_rejects_a_local_only_dataset(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: localonly\nmodels: []\n")
    r = await client.post("/api/datasets/localonly/download")
    assert r.status_code == 400


@pytest.mark.anyio
async def test_download_404s_for_an_unknown_dataset(client, catalog_path):
    catalog_path.write_text("datasets: []\nmodels: []\n")
    r = await client.post("/api/datasets/nope/download")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_a_second_download_for_the_same_dataset_is_rejected(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: rust\n    repo: a/b\n    revision: main\nmodels: []\n")
    assert (await client.post("/api/datasets/rust/download")).status_code == 200
    assert (await client.post("/api/datasets/rust/download")).status_code == 409


@pytest.mark.anyio
async def test_job_status_exposes_meta(client, catalog_path):
    catalog_path.write_text("datasets:\n  - name: rust\n    repo: a/b\n    revision: main\nmodels: []\n")
    jid = (await client.post("/api/datasets/rust/download")).json()["job_id"]
    body = (await client.get(f"/api/jobs/{jid}")).json()
    assert "meta" in body


@pytest.mark.anyio
async def test_dataset_rows_report_auth_required_without_a_token(client, catalog_path, monkeypatch):
    monkeypatch.delenv("PLT_HF_TOKEN", raising=False)
    catalog_path.write_text("datasets:\n  - name: rust\n    repo: a/b\n    revision: main\nmodels: []\n")
    rows = (await client.get("/api/datasets")).json()
    assert next(r for r in rows if r["name"] == "rust")["auth_required"] is True


@pytest.mark.anyio
async def test_auth_not_required_when_a_token_is_set(client, catalog_path, monkeypatch):
    monkeypatch.setenv("PLT_HF_TOKEN", "hf_example")
    catalog_path.write_text("datasets:\n  - name: rust\n    repo: a/b\n    revision: main\nmodels: []\n")
    rows = (await client.get("/api/datasets")).json()
    assert next(r for r in rows if r["name"] == "rust")["auth_required"] is False


@pytest.mark.anyio
async def test_model_download_queues_a_job(client, catalog_path):
    catalog_path.write_text(
        "datasets: []\nmodels:\n  - name: yolo\n    repo: a/m\n    file: yolo.pt\n")
    r = await client.post("/api/models/yolo/download")
    assert r.status_code == 200
    assert isinstance(r.json()["job_id"], int)


@pytest.mark.anyio
async def test_model_download_rejects_an_entry_with_no_file(client, catalog_path):
    catalog_path.write_text("datasets: []\nmodels:\n  - name: yolo\n    repo: a/m\n")
    r = await client.post("/api/models/yolo/download")
    assert r.status_code == 400
