"""The `.plt-sync.json` marker that records how a dataset got here.

Written by the download job. Its absence means the dataset was never
downloaded — a purely local one — which is a complete, usable state. A
marker that exists but cannot be read, or says the download did not
finish, means the opposite: we cannot vouch for what is on disk.
"""
import json
from pathlib import Path

SYNC_FILE = ".plt-sync.json"


def read_sync(dataset_dir) -> dict | None:
    p = Path(dataset_dir) / SYNC_FILE
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_sync(dataset_dir, *, revision: str, completed: bool) -> None:
    p = Path(dataset_dir) / SYNC_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"revision": revision, "completed": completed}, indent=2))


def is_complete(dataset_dir) -> bool:
    p = Path(dataset_dir) / SYNC_FILE
    if not p.is_file():
        return True                      # never downloaded; a local dataset
    data = read_sync(dataset_dir)
    if data is None:
        return False                     # unreadable; cannot vouch for it
    return bool(data.get("completed"))
