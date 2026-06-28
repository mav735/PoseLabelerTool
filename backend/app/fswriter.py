import shutil
import threading
from pathlib import Path
from app.dataset import append_line, prune_stems

TRASH = ".trash"
# Serializes all filesystem writes within ONE process; deploy must run uvicorn --workers 1.
_lock = threading.Lock()


def _safe_stem(stem: str) -> str:
    if not isinstance(stem, str) or not stem.isdigit():
        raise ValueError(f"invalid stem: {stem!r}")
    return stem


def write_label(dataset_dir: Path, stem: str, text: str) -> None:
    with _lock:
        _safe_stem(stem)
        (Path(dataset_dir) / "labels" / f"{stem}.txt").write_text(text)


def clear_label(dataset_dir: Path, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        (Path(dataset_dir) / "labels" / f"{stem}.txt").write_text("")


def append_keep(dataset_dir: Path, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        append_line(Path(dataset_dir) / "reviewed_keep.txt", stem)


def prune_from_lists(dataset_dir: Path, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        prune_stems(Path(dataset_dir) / "bad_labels.txt", {stem})
        prune_stems(Path(dataset_dir) / "model_labeled.txt", {stem})


def _trash_dir(dataset_dir: Path) -> Path:
    d = Path(dataset_dir) / TRASH
    d.mkdir(parents=True, exist_ok=True)
    return d


def move_to_trash(dataset_dir: Path, stem: str) -> None:
    with _lock:
        _safe_stem(stem)
        td = _trash_dir(dataset_dir)
        img = Path(dataset_dir) / "images" / f"{stem}.jpg"
        lbl = Path(dataset_dir) / "labels" / f"{stem}.txt"
        if img.exists():
            shutil.move(str(img), str(td / f"{stem}.jpg"))
        if lbl.exists():
            shutil.move(str(lbl), str(td / f"{stem}.txt"))


def restore_from_trash(dataset_dir: Path, stem: str) -> bool:
    with _lock:
        _safe_stem(stem)
        td = Path(dataset_dir) / TRASH
        timg = td / f"{stem}.jpg"
        if not timg.exists():
            return False
        shutil.move(str(timg), str(Path(dataset_dir) / "images" / f"{stem}.jpg"))
        tlbl = td / f"{stem}.txt"
        if tlbl.exists():
            shutil.move(str(tlbl), str(Path(dataset_dir) / "labels" / f"{stem}.txt"))
        return True


def list_trash(dataset_dir: Path) -> list:
    td = Path(dataset_dir) / TRASH
    if not td.exists():
        return []
    return sorted(p.stem for p in td.glob("*.jpg"))


def write_bad_labels(dataset_dir, lines) -> None:
    with _lock:
        (Path(dataset_dir) / "bad_labels.txt").write_text("\n".join(lines) + ("\n" if lines else ""))


def purge_trash(dataset_dir: Path, stem: str | None = None) -> int:
    with _lock:
        if stem is not None:
            _safe_stem(stem)
        td = Path(dataset_dir) / TRASH
        if not td.exists():
            return 0
        stems = [stem] if stem is not None else sorted(p.stem for p in td.glob("*.jpg"))
        n = 0
        for s in stems:
            removed = False
            for ext in ("jpg", "txt"):
                f = td / f"{s}.{ext}"
                if f.exists():
                    f.unlink()
                    removed = True
            if removed:
                n += 1
        return n
