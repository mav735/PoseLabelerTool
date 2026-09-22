"""The body of a sync job: commit local changes back to the repo."""
import re
from pathlib import Path

from app.catalog import load_catalog
from app.datasets_mgr import safe_dataset_path
from app.hf.changes import coalesce, pending_rows
from app.hf.client import HFConflict
from app.sync_state import is_diverged, mark_diverged, read_sync, write_sync

# A full 40-character hex commit SHA. Phase 2 allows a catalog `revision` to
# pin a dataset to a commit or a tag; you cannot commit onto anything but a
# branch, so a pinned SHA fails every sync forever. A tag is legitimate and
# indistinguishable from a branch name by shape, so only the SHA case -- the
# one we can actually detect -- is refused.
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def run_sync(session, cfg, job, client) -> None:
    # Jobs are durable rows: an operator who hits trouble, flips this off and
    # restarts must not have a queued sync job picked up and committed anyway.
    # getattr so existing configs that omit the field keep working.
    if not getattr(cfg, "sync_enabled", True):
        return
    cat = load_catalog(cfg.catalog_path)
    entry = next((d for d in cat.datasets if d.name == job.dataset), None)
    if entry is None or not entry.repo:
        return
    ds_dir = safe_dataset_path(cfg.datasets_root, job.dataset)

    if _COMMIT_SHA_RE.match(entry.revision or ""):
        # You cannot commit onto a pinned commit SHA -- only a branch. Refuse
        # clearly rather than attempting it and accumulating rows forever
        # with nothing explaining why.
        job.message = "revision is a pinned commit; sync refused"
        session.commit()
        return

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
