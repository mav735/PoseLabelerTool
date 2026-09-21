from app.dataset_paths import image_path, label_path
from app.dataset import image_dims
from app.labels import parse_label


def label_payload(dataset_dir, shard: str, stem: str) -> dict:
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
