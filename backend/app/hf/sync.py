"""The body of a sync job: commit local changes back to the repo."""
from pathlib import Path

from app.catalog import load_catalog
from app.datasets_mgr import safe_dataset_path
from app.hf.changes import coalesce, pending_rows
from app.hf.client import HFConflict
from app.sync_state import is_diverged, mark_diverged, read_sync, write_sync


def run_sync(session, cfg, job, client) -> None:
    cat = load_catalog(cfg.catalog_path)
    entry = next((d for d in cat.datasets if d.name == job.dataset), None)
    if entry is None or not entry.repo:
        return
    ds_dir = safe_dataset_path(cfg.datasets_root, job.dataset)

    # Refuse rather than overwrite: the remote has moved and a human has not
    # yet decided what to do about it.
    if is_diverged(ds_dir):
        job.message = "dataset diverged; sync paused"
        session.commit()
        return

    rows = pending_rows(session, job.dataset)
    if not rows:
        return

    marker = read_sync(ds_dir) or {}
    parent = marker.get("revision") or None
    if not parent:
        # Without a known parent, create_commit does NO precondition check and
        # would write blind to the live branch. A missing or unparseable marker
        # is exactly the state where we cannot know what the remote holds.
        job.message = "no known revision for this dataset; sync refused"
        session.commit()
        return

    adds, deletes = [], []
    for path, op in sorted(coalesce(rows).items()):
        if op == "delete":
            deletes.append(path)
            continue
        local = Path(ds_dir) / path
        if local.is_file():
            adds.append((path, str(local)))
        # A vanished local file is a stale row: dropping it is right, and
        # keeping it would fail every future commit for this dataset.

    if not adds and not deletes:
        for r in rows:
            session.delete(r)
        session.commit()
        return

    message = f"labels: {len(adds)} updated, {len(deletes)} removed"
    try:
        sha = client.commit(entry.repo, entry.revision, adds, deletes,
                            message, parent_commit=parent)
    except HFConflict:
        mark_diverged(ds_dir)
        session.commit()
        raise

    write_sync(ds_dir, revision=sha or parent, completed=True)
    for r in rows:
        session.delete(r)
    job.result = {"adds": len(adds), "deletes": len(deletes), "revision": sha}
    session.commit()
