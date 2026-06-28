import threading

_models = {}
_lock = threading.Lock()


def iou(a, b) -> float:
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def suppress_overlaps(preds, iou_thr=0.0):
    order = sorted(preds, key=lambda p: p[1], reverse=True)
    kept = []
    for p in order:
        if all(iou(p[0], k[0]) <= iou_thr for k in kept):
            kept.append(p)
    return kept


def pred_to_instances(preds):
    out = []
    for _box, _conf, kpts in preds:
        inst = []
        for k in range(min(15, len(kpts))):
            kx, ky, kc = float(kpts[k][0]), float(kpts[k][1]), float(kpts[k][2])
            v = 2 if kc > 0.5 else (1 if kc > 0.15 else 0)
            inst.append([kx, ky, v])
        while len(inst) < 15:
            inst.append([0.0, 0.0, 0])
        out.append({"kpts": inst})
    return out


def device():
    import torch
    return 0 if torch.cuda.is_available() else "cpu"


def load_model(path: str):
    with _lock:
        if path not in _models:
            from ultralytics import YOLO
            _models[path] = YOLO(path)
        return _models[path]


def run_pred(model, source, conf=0.15, iou_thr=0.45):
    results = model.predict(source, imgsz=640, conf=conf, iou=iou_thr, verbose=False, device=device())
    preds = []
    for r in results:
        if r.boxes is None or r.keypoints is None:
            continue
        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        kpts_all = r.keypoints.data.cpu().numpy()
        for i in range(len(boxes)):
            preds.append((boxes[i], float(confs[i]), kpts_all[i]))
    return suppress_overlaps(preds)
