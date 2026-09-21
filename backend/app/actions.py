from pathlib import Path
from app.models import Image, Review
from app import fswriter
from app.labels import Keypoint, fit_box, format_instance, write_label_text
from app.dataset import image_dims
from app.dataset_paths import image_path

ACTIONS = ("keep", "drop", "clear", "replace", "edit")


class UnknownImage(LookupError):
    """No Image row for (dataset, stem), so the shard cannot be resolved."""


def instances_to_text(instances, width, height) -> str:
    lines = []
    for inst in instances or []:
        kpts = [Keypoint(float(x), float(y), int(v)) for x, y, v in inst["kpts"]]
        xs = [k.x for k in kpts if k.v > 0]
        ys = [k.y for k in kpts if k.v > 0]
        box = fit_box(xs, ys, width, height)
        if box is None:
            continue
        lines.append(format_instance(box, kpts, width, height))
    return write_label_text(lines)


def apply_action(session, dataset: str, dataset_dir: Path, stem: str, task: str,
                 user_id: int, action: str, instances=None, width=None,
                 height=None) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    img = session.get(Image, (dataset, stem))
    if img is None:
        # No row means no shard. Falling back to "" would write
        # labels/{stem}.txt at the flat root of a directory that mirrors a
        # remote repository 1:1 -- and write_label creates its parent, so the
        # stray file would appear rather than the write failing. Every caller
        # has a row; demand it instead of guessing.
        raise UnknownImage(f"unknown image: {dataset}/{stem}")
    shard = img.shard
    if action == "keep":
        fswriter.append_keep(dataset_dir, stem)
        img.approved = True
    elif action == "clear":
        fswriter.clear_label(dataset_dir, shard, stem)
        fswriter.append_keep(dataset_dir, stem)
        img.approved = True
        img.has_label = False
    elif action == "drop":
        fswriter.move_to_trash(dataset_dir, shard, stem)
        fswriter.prune_from_lists(dataset_dir, stem)
        img.deleted = True
    else:  # replace | edit
        if width is None or height is None:
            width, height = image_dims(image_path(dataset_dir, shard, stem))
        text = instances_to_text(instances, width, height)
        fswriter.write_label(dataset_dir, shard, stem, text)
        fswriter.append_keep(dataset_dir, stem)
        img.approved = True
        img.has_label = bool(text.strip())
    session.add(Review(dataset=dataset, stem=stem, task=task, user_id=user_id, action=action))
    session.commit()
