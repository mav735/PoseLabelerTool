from pathlib import Path
from app.config import load_config


def test_load_defaults_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "datasets_root: /data/ds\n"
        "models_root: /data/models\n"
        "db_url: postgresql+psycopg://u:p@db:5432/plt\n"
    )
    cfg = load_config(str(cfg_file))
    assert cfg.datasets_root == Path("/data/ds")
    assert cfg.port == 8080
    assert cfg.lease_timeout == 180
    assert cfg.dedup_thresh == 3.0


def test_env_overrides_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "datasets_root: /data/ds\nmodels_root: /data/models\n"
        "db_url: postgresql+psycopg://u:p@db:5432/plt\n"
    )
    monkeypatch.setenv("PLT_PORT", "9000")
    monkeypatch.setenv("PLT_DB_URL", "postgresql+psycopg://x:y@host:5432/other")
    cfg = load_config(str(cfg_file))
    assert cfg.port == 9000
    assert cfg.db_url.endswith("/other")


def test_config_reads_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("PLT_DATASETS_ROOT", str(tmp_path / "ds"))
    monkeypatch.setenv("PLT_MODELS_ROOT", str(tmp_path / "models"))
    monkeypatch.setenv("PLT_DB_URL", "postgresql+psycopg://u:p@h/db")
    cfg = load_config(str(tmp_path / "absent.yaml"))
    assert cfg.datasets_root == tmp_path / "ds"
    assert cfg.models_root == tmp_path / "models"
    assert cfg.catalog_path == Path("datasets.yaml")
    assert cfg.migrate_default_dataset == "default"
