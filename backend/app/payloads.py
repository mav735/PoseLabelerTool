from pathlib import Path
from app.dataset import image_dims
from app.labels import parse_label


def label_payload(dataset_dir, stem: str) -> dict:
    dataset_dir = Path(dataset_dir)
    w, h = image_dims(dataset_dir / "images" / f"{stem}.jpg")
    lbl = dataset_dir / "labels" / f"{stem}.txt"
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
