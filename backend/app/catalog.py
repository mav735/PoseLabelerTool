from pathlib import Path
import yaml
from pydantic import BaseModel, ValidationError


class CatalogError(Exception):
    pass


class DatasetEntry(BaseModel):
    name: str
    repo: str | None = None
    revision: str = "main"


class ModelEntry(BaseModel):
    name: str
    repo: str | None = None
    file: str | None = None


class Catalog(BaseModel):
    datasets: list[DatasetEntry] = []
    models: list[ModelEntry] = []


def load_catalog(path) -> Catalog:
    p = Path(path)
    if not p.exists():
        return Catalog()
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise CatalogError(f"{p}: {e}") from e
    try:
        return Catalog(**data)
    except (ValidationError, TypeError) as e:
        raise CatalogError(f"{p}: {e}") from e


def load_catalog_safe(path) -> tuple[Catalog, str | None]:
    try:
        return load_catalog(path), None
    except CatalogError as e:
        return Catalog(), str(e)


def _write(path: Path, cat: Catalog) -> None:
    payload = {
        "datasets": [d.model_dump(exclude_none=True) for d in cat.datasets],
        "models": [m.model_dump(exclude_none=True) for m in cat.models],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def add_dataset(path, entry: DatasetEntry) -> Catalog:
    p = Path(path)
    cat = load_catalog(p)
    if any(d.name == entry.name for d in cat.datasets):
        raise CatalogError(f"dataset already in catalog: {entry.name}")
    cat.datasets.append(entry)
    _write(p, cat)
    return cat
