from dataclasses import dataclass

NUM_KPTS = 15
BBOX_MARGIN = 0.02
KPT_NAMES = ["hd", "ch", "pl", "ls", "rs", "lh", "rh",
             "lw", "rw", "lf", "rf", "le", "re", "lk", "rk"]
SKELETON = [(0, 1), (1, 2), (1, 3), (1, 4),
            (3, 11), (11, 7), (4, 12), (12, 8),
            (2, 5), (2, 6), (5, 13), (13, 9), (6, 14), (14, 10)]
FLIP_IDX = [0, 1, 2, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13]


@dataclass
class Keypoint:
    x: float
    y: float
    v: int


@dataclass
class Instance:
    cx: float
    cy: float
    w: float
    h: float
    kpts: list


def parse_label(text: str) -> list:
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        cx, cy, w, h = map(float, p[1:5])
        kpts = []
        for k in range(NUM_KPTS):
            b = 5 + k * 3
            if b + 2 < len(p):
                kpts.append(Keypoint(float(p[b]), float(p[b + 1]), int(float(p[b + 2]))))
            else:
                kpts.append(Keypoint(0.0, 0.0, 0))
        out.append(Instance(cx, cy, w, h, kpts))
    return out


def fit_box(xs, ys, w_bound, h_bound, margin=BBOX_MARGIN):
    if not xs:
        return None
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    mw, mh = (maxx - minx) * margin, (maxy - miny) * margin
    return (max(0.0, minx - mw), max(0.0, miny - mh),
            min(float(w_bound), maxx + mw), min(float(h_bound), maxy + mh))


def format_instance(box, kpts, w, h) -> str:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2) / w
    cy = ((y1 + y2) / 2) / h
    bw = (x2 - x1) / w
    bh = (y2 - y1) / h
    parts = [f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"]
    for kp in kpts:
        parts.append(f"{kp.x / w:.6f} {kp.y / h:.6f} {kp.v}")
    return " ".join(parts)


def write_label_text(lines) -> str:
    return "\n".join(lines) + ("\n" if lines else "")
