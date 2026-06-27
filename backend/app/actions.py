from pathlib import Path
from app.models import Image, Review
from app import fswriter
from app.labels import Keypoint, fit_box, format_instance, write_label_text

ACTIONS = ("keep", "drop", "clear", "replace", "edit")


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


def apply_action(session, dataset_dir: Path, stem: str, task: str, user_id: int,
                 action: str, instances=None, width=None, height=None) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    img = session.get(Image, stem)
    if action == "keep":
        fswriter.append_keep(dataset_dir, stem)
        if img:
            img.approved = True
    elif action == "clear":
        fswriter.clear_label(dataset_dir, stem)
        fswriter.append_keep(dataset_dir, stem)
        if img:
            img.approved = True
            img.has_label = False
    elif action == "drop":
        fswriter.move_to_trash(dataset_dir, stem)
        fswriter.prune_from_lists(dataset_dir, stem)
        if img:
            img.deleted = True
    else:  # replace | edit
        text = instances_to_text(instances, width, height)
        fswriter.write_label(dataset_dir, stem, text)
        fswriter.append_keep(dataset_dir, stem)
        if img:
            img.approved = True
            img.has_label = bool(text.strip())
    session.add(Review(stem=stem, task=task, user_id=user_id, action=action))
    session.commit()
