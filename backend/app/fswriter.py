import re
import shutil
import threading
from pathlib import Path
from app.dataset import append_line, prune_stems
from app.dataset_paths import (image_path, label_path, trash_image_path,
                                trash_label_path, safe_shard, repo_rel_image,
                                repo_rel_label)

TRASH = ".trash"
# Stems are pure digits ("100") or digit groups joined by "_" ("1_00000297").
_STEM_RE = re.compile(r"^\d+(_\d+)*$")
# Serializes all filesystem writes within ONE process; deploy must run uvicorn --workers 1.
_lock = threading.Lock()

_sink = None


def set_change_sink(fn) -> None:
    """Install a callback fired for every mutation, or None to disable.

    Module-level state, deliberately: the alternative was threading a session
    through actions.py, jobs.py and main.py. Tests inject a fake and restore it.
    """
    global _sink
    _sink = fn


def _record(dataset_dir, path: str, op: str) -> None:
    if _sink is not None:
        _sink(dataset_dir, path, op)


def is_valid_stem(stem) -> bool:
    return isinstance(stem, str) and _STEM_RE.fullmatch(stem) is not None


def _safe_stem(stem: str) -> str:
    if not is_valid_stem(stem):
        raise ValueError(f"invalid stem: {stem!r}")
    return stem


def write_label(dataset_dir: Path, shard: str, stem: str, text: str) -> None:
    with _lock:
        _safe_stem(stem)
        p = label_path(dataset_dir, shard, stem)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        _record(dataset_dir, repo_rel_label(shard, stem), "add")


def clear_label(dataset_dir: Path, shard: str, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        p = label_path(dataset_dir, shard, stem)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
        _record(dataset_dir, repo_rel_label(shard, stem), "add")


def append_keep(dataset_dir: Path, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        append_line(Path(dataset_dir) / "reviewed_keep.txt", stem)
        _record(dataset_dir, "reviewed_keep.txt", "add")


def prune_from_lists(dataset_dir: Path, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        prune_stems(Path(dataset_dir) / "bad_labels.txt", {stem})
        prune_stems(Path(dataset_dir) / "model_labeled.txt", {stem})
        _record(dataset_dir, "bad_labels.txt", "add")
        _record(dataset_dir, "model_labeled.txt", "add")


def move_to_trash(dataset_dir: Path, shard: str, stem: str) -> bool:
    """Move an image and its label into the trash; True if the image moved.

    False means the image was not where ``shard`` said it was -- a wrong shard
    on a sharded dataset looks exactly like this. A caller that reports the
    deletion as done on a False has told the operator something untrue, so the
    answer is returned rather than swallowed.
    """
    with _lock:
        _safe_stem(stem)
        moved = image_path(dataset_dir, shard, stem).exists()
        for src, dst in ((image_path(dataset_dir, shard, stem),
                          trash_image_path(dataset_dir, shard, stem)),
                         (label_path(dataset_dir, shard, stem),
                          trash_label_path(dataset_dir, shard, stem))):
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
        if moved:
            _record(dataset_dir, repo_rel_image(shard, stem), "delete")
            _record(dataset_dir, repo_rel_label(shard, stem), "delete")
        return moved


def restore_from_trash(dataset_dir: Path, shard: str, stem: str) -> bool:
    with _lock:
        _safe_stem(stem)
        timg = trash_image_path(dataset_dir, shard, stem)
        if not timg.exists():
            return False
        moved_paths = []
        for src, dst, rel in (
            (timg, image_path(dataset_dir, shard, stem),
             repo_rel_image(shard, stem)),
            (trash_label_path(dataset_dir, shard, stem),
             label_path(dataset_dir, shard, stem),
             repo_rel_label(shard, stem)),
        ):
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved_paths.append(rel)
        for rel in moved_paths:
            _record(dataset_dir, rel, "add")
        return True


def _trash_entries(dataset_dir: Path):
    """Yield (shard, stem) for everything currently in the trash."""
    td = Path(dataset_dir) / TRASH
    if not td.is_dir():
        return
    for entry in td.iterdir():
        if entry.is_file() and entry.suffix == ".jpg":
            yield "", entry.stem
        elif entry.is_dir():
            try:
                shard = safe_shard(entry.name)
            except ValueError:
                continue
            for f in entry.iterdir():
                if f.is_file() and f.suffix == ".jpg":
                    yield shard, f.stem


def list_trash(dataset_dir: Path) -> list:
    return sorted(stem for _shard, stem in _trash_entries(dataset_dir))


def write_bad_labels(dataset_dir, lines) -> None:
    with _lock:
        (Path(dataset_dir) / "bad_labels.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        _record(dataset_dir, "bad_labels.txt", "add")


def purge_trash(dataset_dir: Path, *, shard: str = "", stem: str | None = None) -> int:
    """Delete one trashed stem, or -- with no stem -- the entire trash.

    ``shard`` is keyword-only. Positionally, ``purge_trash(dd, "003")`` reads
    as "purge shard 003" and never meant that: with no stem the whole trash
    goes, across every shard. Keyword-only also turns a stale call written
    against the old ``(dataset_dir, stem)`` signature into a TypeError rather
    than a silent purge-everything, and the guard below rejects the one
    spelling that survives it.
    """
    with _lock:
        if stem is not None:
            _safe_stem(stem)
            targets = [(shard, stem)]
        else:
            if shard:
                raise ValueError(
                    "purge_trash: a shard without a stem would purge the whole "
                    "trash; pass a stem, or drop the shard to mean that")
            targets = list(_trash_entries(dataset_dir))
        n = 0
        for sh, st in targets:
            removed = False
            for p in (trash_image_path(dataset_dir, sh, st),
                      trash_label_path(dataset_dir, sh, st)):
                if p.exists():
                    p.unlink()
                    removed = True
            if removed:
                n += 1
        return n
