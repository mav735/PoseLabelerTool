from pathlib import Path
from app.catalog import Catalog
from app.sync_state import is_complete


def safe_dataset_path(datasets_root, name: str) -> Path:
    base = Path(datasets_root).resolve()
    if (not name or name.startswith(".")
            or any(c in name for c in ("..", "/", "\\"))):
        raise ValueError(f"invalid dataset: {name!r}")
    p = (base / name).resolve()
    if base != p and base not in p.parents:
        raise ValueError(f"invalid dataset path: {name!r}")
    # Check case sensitivity: if path exists, name must match on-disk spelling
    if p.exists() and base.is_dir():
        if name not in {c.name for c in base.iterdir()}:
            raise ValueError(f"dataset name case does not match disk: {name!r}")
    return p


def is_ready(path: Path) -> bool:
    return (Path(path) / "images").is_dir() and is_complete(path)


def dir_size(path: Path) -> int:
    total = 0
    for f in Path(path).rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def discover(datasets_root) -> list[str]:
    root = Path(datasets_root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and (p / "images").is_dir())


def list_status(datasets_root, cat: Catalog, *, token_present: bool = True) -> list[dict]:
    root = Path(datasets_root)
    entries = {d.name: d for d in cat.datasets}
    names = sorted(set(entries) | set(discover(root)))
    rows = []
    for name in names:
        entry = entries.get(name)
        try:
            path = safe_dataset_path(root, name)
        except ValueError:
            continue
        local = path.is_dir()
        repo = entry.repo if entry else None
        rows.append({
            "name": name,
            "repo": repo,
            "revision": entry.revision if entry else "main",
            "local": local,
            "ready": local and is_ready(path),
            "size_bytes": dir_size(path) if local else 0,
            "auth_required": bool(repo) and not token_present,
        })
    return rows
