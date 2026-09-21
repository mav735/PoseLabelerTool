"""The only place that builds paths inside a dataset directory.

A dataset is either flat (``images/100.jpg``) or sharded one level deep
(``images/000/100.jpg``). ``shard == ""`` means flat. Every caller goes
through here so the two shapes are handled in exactly one place.
"""
import re
from pathlib import Path
from typing import Iterator

IMAGES = "images"
LABELS = "labels"
TRASH = ".trash"

# A shard is one path component: a directory name, never a path.
_SHARD_RE = re.compile(r"^[A-Za-z0-9_-]{1,8}$")


def safe_shard(shard: str) -> str:
    if shard == "":
        return ""
    if not isinstance(shard, str) or _SHARD_RE.fullmatch(shard) is None:
        raise ValueError(f"invalid shard: {shard!r}")
    return shard


def _under(dataset_dir, top: str, shard: str, name: str) -> Path:
    safe_shard(shard)
    base = Path(dataset_dir) / top
    return (base / shard / name) if shard else (base / name)


def image_path(dataset_dir, shard: str, stem: str) -> Path:
    return _under(dataset_dir, IMAGES, shard, f"{stem}.jpg")


def label_path(dataset_dir, shard: str, stem: str) -> Path:
    return _under(dataset_dir, LABELS, shard, f"{stem}.txt")


def trash_image_path(dataset_dir, shard: str, stem: str) -> Path:
    return _under(dataset_dir, TRASH, shard, f"{stem}.jpg")


def trash_label_path(dataset_dir, shard: str, stem: str) -> Path:
    return _under(dataset_dir, TRASH, shard, f"{stem}.txt")


def iter_image_files(dataset_dir) -> Iterator[tuple[str, str]]:
    """Yield (shard, stem) for every image, flat or one level of shard."""
    base = Path(dataset_dir) / IMAGES
    if not base.is_dir():
        return
    for entry in base.iterdir():
        if entry.is_file() and entry.suffix == ".jpg":
            yield "", entry.stem
        elif entry.is_dir():
            try:
                shard = safe_shard(entry.name)
            except ValueError:
                continue          # not a shard we recognise; ignore it
            for f in entry.iterdir():
                if f.is_file() and f.suffix == ".jpg":
                    yield shard, f.stem
