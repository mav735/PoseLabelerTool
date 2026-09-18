from pathlib import Path
from PIL import Image as PILImage
from app.models import Image


def read_stem_list(path: Path) -> set:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.add(line.split()[0])
    return out


def append_line(path: Path, stem: str):
    if stem in read_stem_list(path):
        return
    with open(path, "a") as f:
        f.write(f"{stem}\n")


def prune_stems(path: Path, stems: set):
    if not path.exists():
        return
    kept = [ln for ln in path.read_text().splitlines()
            if ln.strip() and ln.split()[0] not in stems]
    path.write_text("\n".join(kept) + ("\n" if kept else ""))


def image_dims(path: Path):
    try:
        with PILImage.open(path) as im:
            return im.width, im.height
    except Exception:
        return (0, 0)


def image_stems(dataset_dir) -> list:
    img_dir = Path(dataset_dir) / "images"
    stems = [p.stem for p in img_dir.glob("*.jpg")]
    stems.sort(key=lambda s: (0, int(s)) if s.isdigit() else (1, s))
    return stems


def scan(session, dataset: str, dataset_dir: Path) -> dict:
    dataset_dir = Path(dataset_dir)
    img_dir = dataset_dir / "images"
    lbl_dir = dataset_dir / "labels"
    approved = read_stem_list(dataset_dir / "reviewed_keep.txt")
    model_labeled = read_stem_list(dataset_dir / "model_labeled.txt")
    bad = read_stem_list(dataset_dir / "bad_labels.txt")

    seen = set()
    for ip in sorted(img_dir.glob("*.jpg")):
        stem = ip.stem
        seen.add(stem)
        lbl = lbl_dir / f"{stem}.txt"
        has_label = lbl.exists() and lbl.read_text().strip() != ""
        w, h = image_dims(ip)
        row = session.get(Image, (dataset, stem))
        if row is None:
            row = Image(dataset=dataset, stem=stem)
            session.add(row)
        row.width, row.height = w, h
        row.has_label = has_label
        row.in_model_labeled = stem in model_labeled
        row.in_bad_labels = stem in bad
        row.approved = stem in approved
        row.deleted = False
    for row in session.query(Image).filter(Image.dataset == dataset).all():
        if row.stem not in seen:
            row.deleted = True
    session.commit()
    return {"scanned": len(seen), "approved": len(approved),
            "model_labeled": len(model_labeled), "bad": len(bad)}
