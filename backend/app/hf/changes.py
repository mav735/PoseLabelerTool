"""Records repo-relevant filesystem changes for later commit."""
from pathlib import Path

from sqlalchemy import select

from app.catalog import load_catalog_safe
from app.models import PendingChange

# Only these two trees are repo content. reviewed_keep.txt, bad_labels.txt and
# model_labeled.txt are per-installation review state; the real repo holds no
# such files, and pushing them would publish one reviewer's workflow.
REPO_PREFIXES = ("images/", "labels/")


def is_repo_content(path: str) -> bool:
    return path.startswith(REPO_PREFIXES)


def record(session_factory, catalog_path, dataset_dir, path: str, op: str) -> None:
    """Persist one change, if it is repo content for a dataset with a repo.

    The dataset name is the directory's own name: `safe_dataset_path` builds
    every dataset directory as `<datasets_root>/<name>`, so the basename IS the
    catalogue key, and fswriter never has to learn about datasets.
    """
    if not is_repo_content(path):
        return
    name = Path(dataset_dir).name
    cat, _err = load_catalog_safe(catalog_path)
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
    return len(pending_rows(session, dataset))


def pending_list(session, dataset: str):
    return pending_rows(session, dataset)
