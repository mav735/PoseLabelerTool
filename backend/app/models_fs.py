from pathlib import Path


def list_models(models_dir) -> list:
    base = Path(models_dir)
    out = []
    if base.exists():
        for p in base.rglob("*.pt"):
            out.append({"name": p.name, "path": p.relative_to(base).as_posix()})
    out.sort(key=lambda m: m["path"])
    return out
