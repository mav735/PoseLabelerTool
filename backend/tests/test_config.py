from pathlib import Path
from app.config import load_config


def test_load_defaults_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "dataset_dir: /data/ds\n"
        "models_dir: /data/models\n"
        "db_url: postgresql+psycopg://u:p@db:5432/plt\n"
    )
    cfg = load_config(str(cfg_file))
    assert cfg.dataset_dir == Path("/data/ds")
    assert cfg.port == 8080
    assert cfg.lease_timeout == 180
    assert cfg.bbox_margin == 0.02
    assert cfg.dedup_thresh == 3.0


def test_env_overrides_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "dataset_dir: /data/ds\nmodels_dir: /data/models\n"
        "db_url: postgresql+psycopg://u:p@db:5432/plt\n"
    )
    monkeypatch.setenv("PLT_PORT", "9000")
    monkeypatch.setenv("PLT_DB_URL", "postgresql+psycopg://x:y@host:5432/other")
    cfg = load_config(str(cfg_file))
    assert cfg.port == 9000
    assert cfg.db_url.endswith("/other")
