import math


def bbox_iou(b1, b2) -> float:
    x1 = max(b1[0] - b1[2] / 2, b2[0] - b2[2] / 2)
    y1 = max(b1[1] - b1[3] / 2, b2[1] - b2[3] / 2)
    x2 = min(b1[0] + b1[2] / 2, b2[0] + b2[2] / 2)
    y2 = min(b1[1] + b1[3] / 2, b2[1] + b2[3] / 2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    a1 = b1[2] * b1[3]
    a2 = b2[2] * b2[3]
    return inter / (a1 + a2 - inter + 1e-6)


def kpt_distance(gt_kpts, pred_kpts, bbox_area) -> float:
    dists = []
    scale = max(math.sqrt(bbox_area), 1.0)
    for k in range(min(len(gt_kpts), len(pred_kpts))):
        gx, gy, gv = gt_kpts[k]
        if gv == 0:
            continue
        px, py, pc = pred_kpts[k]
        if pc < 0.1:
            dists.append(1.0)
            continue
        d = math.sqrt((gx - px) ** 2 + (gy - py) ** 2) / scale
        dists.append(min(d, 1.0))
    return sum(dists) / len(dists) if dists else 0.0


def _fp_penalty(n: int) -> float:
    return min(1.0, 0.5 + 0.15 * n)


def score_image_a(gt, preds, fp_conf=0.5):
    if not gt:
        fps = sum(1 for p in preds if p["conf"] >= fp_conf)
        if fps:
            return _fp_penalty(fps), f"FP on bg: {fps} pred(s)"
        return 0.0, "background"
    if not preds:
        return 1.0, f"missed {len(gt)} GT"
    matched = set()
    errors = []
    for g in gt:
        best_err, best_reason, best_idx = 1.0, "no match", -1
        for i, p in enumerate(preds):
            iou = bbox_iou(g["bbox"], p["bbox"])
            if iou < 0.3:
                continue
            area = g["bbox"][2] * g["bbox"][3]
            kd = kpt_distance(g["kpts"], p["kpts"], area)
            err = 0.3 * (1 - iou) + 0.7 * kd
            if err < best_err:
                best_err, best_reason, best_idx = err, f"iou={iou:.2f} kd={kd:.3f}", i
        if best_idx >= 0:
            matched.add(best_idx)
        errors.append((best_err, best_reason))
    worst_err, worst_reason = max(errors, key=lambda x: x[0])
    fps = sum(1 for i, p in enumerate(preds) if i not in matched and p["conf"] >= fp_conf)
    if fps:
        fe = _fp_penalty(fps)
        if fe > worst_err:
            return fe, f"{fps} FP (extra pred)"
        worst_reason += f" +{fps}FP"
    return worst_err, worst_reason


def score_image_b(gt, preds, fp_conf=0.5, min_side=40.0):
    worst, worst_reason = 0.0, "ok"
    for g in gt:
        for p in preds:
            if p["conf"] < fp_conf:
                continue
            if max(p["bbox"][2], p["bbox"][3]) < min_side:
                continue
            if bbox_iou(g["bbox"], p["bbox"]) < 0.3:
                continue
            area = g["bbox"][2] * g["bbox"][3]
            scale = max(math.sqrt(area), 1.0)
            md = 0.0
            for k in range(15):
                gx, gy, _ = g["kpts"][k]
                px, py, _ = p["kpts"][k]
                md = max(md, math.sqrt((gx - px) ** 2 + (gy - py) ** 2) / scale)
            if md > worst:
                worst, worst_reason = md, f"max-dist={md:.3f}"
    return worst, worst_reason
