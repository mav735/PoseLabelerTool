import os
from pathlib import Path
import yaml
from pydantic import BaseModel

ENV_PREFIX = "PLT_"


class Config(BaseModel):
    datasets_root: Path
    models_root: Path
    db_url: str
    catalog_path: Path = Path("datasets.yaml")
    migrate_default_dataset: str = "default"
    port: int = 8080
    lease_timeout: int = 180
    heartbeat_interval: int = 30
    oracle_conf: float = 0.15
    oracle_threshold: float = 0.3
    dedup_thresh: float = 3.0
    dedup_hash: int = 32


def load_config(path: str | None = None) -> Config:
    path = path or os.environ.get("PLT_CONFIG", "config.yaml")
    data = {}
    p = Path(path)
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
    for field in Config.model_fields:
        env = os.environ.get(ENV_PREFIX + field.upper())
        if env is not None:
            data[field] = env
    return Config(**data)
