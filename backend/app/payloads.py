from app.dataset_paths import image_path, label_path
from app.dataset import image_dims
from app.labels import parse_label


def label_payload(dataset_dir, shard: str, stem: str) -> dict:
    """Build the lease/image payload for one stem.

    Keypoints (and box fields) come straight from the YOLO label file, so
    they are NORMALIZED (0-1) here. `/api/submit` expects pixel coordinates
    instead (see `actions.instances_to_text`) -- the frontend converts.
    """
    w, h = image_dims(image_path(dataset_dir, shard, stem))
    lbl = label_path(dataset_dir, shard, stem)
    text = lbl.read_text() if lbl.exists() else ""
    insts = parse_label(text)
    return {
        "stem": stem, "width": w, "height": h,
        "instances": [
            {"cx": i.cx, "cy": i.cy, "w": i.w, "h": i.h,
             "kpts": [[k.x, k.y, k.v] for k in i.kpts]}
            for i in insts
        ],
    }
