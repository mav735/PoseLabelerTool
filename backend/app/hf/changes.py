"""Records repo-relevant filesystem changes for later commit."""
import threading
from pathlib import Path

from sqlalchemy import select

from app.catalog import load_catalog_safe
from app.models import PendingChange

# Only these two trees are repo content. reviewed_keep.txt, bad_labels.txt and
# model_labeled.txt are per-installation review state; the real repo holds no
# such files, and pushing them would publish one reviewer's workflow.
REPO_PREFIXES = ("images/", "labels/")

# record() runs inside fswriter's process-wide lock (every filesystem write
# in the process is serialized behind it), so re-parsing datasets.yaml's YAML
# on every single label write, keep-append and trash move is pure waste.
# Cache the parsed catalog keyed on the file's path and mtime; a changed
# mtime invalidates the entry. A module-level dict guarded by a small lock,
# not the fswriter lock -- callers of this cache do not need to be callers
# of fswriter.
_catalog_cache_lock = threading.Lock()
_catalog_cache: dict[str, tuple[float | None, tuple]] = {}


def _load_catalog_cached(catalog_path):
    p = Path(catalog_path)
    key = str(p)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = None
    with _catalog_cache_lock:
        cached = _catalog_cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
    result = load_catalog_safe(catalog_path)
    with _catalog_cache_lock:
        _catalog_cache[key] = (mtime, result)
    return result


def is_repo_content(path: str) -> bool:
    return path.startswith(REPO_PREFIXES)


def record(session_factory, catalog_path, dataset_dir, path: str, op: str) -> None:
    """Persist one change, if it is repo content for a dataset with a repo.

    The dataset name is the directory's own name: `safe_dataset_path` builds
    every dataset directory as `<datasets_root>/<name>`, so the basename IS the
    catalogue key, and fswriter never has to learn about datasets.

    Deliberately not wrapped in try/except: apply_action commits a Review row
    right after the filesystem write that leads here, so if the database is
    unavailable the request fails regardless -- this call is not what breaks
    it. Swallowing an error here would instead create a silently unsynced
    edit with no reconciliation path, which is worse than a visible error the
    user can retry.
    """
    if not is_repo_content(path):
        return
    name = Path(dataset_dir).name
    cat, _err = _load_catalog_cached(catalog_path)
    entry = next((d for d in cat.datasets if d.name == name), None)
    if entry is None or not entry.repo:
        return
    session = session_factory()
    try:
        session.add(PendingChange(dataset=name, path=path, op=op))
        session.commit()
    finally:
        session.close()


def coalesce(rows) -> dict[str, str]:
    """Last op per path wins. Ten edits to one label become one add."""
    out: dict[str, str] = {}
    for r in rows:
        out[r.path] = r.op
    return out


def pending_rows(session, dataset: str):
    return list(session.execute(
        select(PendingChange).where(PendingChange.dataset == dataset)
        .order_by(PendingChange.id)).scalars())


def pending_count(session, dataset: str) -> int:
    """How many FILES are unpushed — not how many edit events were recorded.

    Rows are per-mutation and `coalesce` collapses them by path before any
    commit, so distinct paths is both what a sync will actually send and the
    number a reviewer means by "unsynced work". Counting rows would report 50
    for one label edited 50 times, and would trip sync_max_pending for a commit
    containing a single file.
    """
    return len({r.path for r in pending_rows(session, dataset)})


def pending_list(session, dataset: str):
    return pending_rows(session, dataset)
