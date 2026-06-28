from pathlib import Path


def safe_model_path(models_dir, model: str):
    base = Path(models_dir).resolve()
    if not model or any(c in model for c in ("..", "\\")) or model.startswith("/"):
        raise ValueError(f"invalid model: {model!r}")
    p = (base / model).resolve()
    if base != p and base not in p.parents:
        raise ValueError(f"invalid model path: {model!r}")
    return p


def list_models(models_dir) -> list:
    base = Path(models_dir)
    out = []
    if base.exists():
        for p in base.rglob("*.pt"):
            out.append({"name": p.name, "path": p.relative_to(base).as_posix()})
    out.sort(key=lambda m: m["path"])
    return out
