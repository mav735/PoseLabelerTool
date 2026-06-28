from pathlib import Path
from PIL import Image as PILImage
from sqlalchemy import select
from app import inference, oracle, dedup, fswriter
from app.labels import parse_label
from app.dataset import image_stems, read_stem_list
from app.models import Image, Job, DedupPair
from app.models_fs import safe_model_path


def _gt_pixels(text, w, h):
    out = []
    for inst in parse_label(text):
        out.append({
            "bbox": (inst.cx * w, inst.cy * h, inst.w * w, inst.h * h),
            "kpts": [(k.x * w, k.y * h, k.v) for k in inst.kpts],
        })
    return out


def run_oracle(session, cfg, job, params):
    dataset = Path(cfg.dataset_dir)
    approved = read_stem_list(dataset / "reviewed_keep.txt")
    stems = [s for s in image_stems(dataset) if s not in approved]
    model = inference.load_model(str(safe_model_path(cfg.models_dir, params["model"])))
    mode = params.get("mode", "a")
    thr = float(params.get("threshold", 0.3))
    job.total = len(stems)
    session.commit()
    scored = []
    for i, stem in enumerate(stems):
        img = dataset / "images" / f"{stem}.jpg"
        lbl = dataset / "labels" / f"{stem}.txt"
        try:
            with PILImage.open(img) as im:
                w, h = im.width, im.height
        except Exception:
            continue
        gt = _gt_pixels(lbl.read_text() if lbl.exists() else "", w, h)
        raw = inference.run_pred(model, str(img))
        preds = [{"bbox": _xyxy_to_cxcywh(b), "conf": c,
                  "kpts": [(float(k[0]), float(k[1]), float(k[2])) for k in kp]} for b, c, kp in raw]
        if mode == "b":
            sc, reason = oracle.score_image_b(gt, preds)
        else:
            sc, reason = oracle.score_image_a(gt, preds)
        if sc >= thr:
            scored.append((sc, stem, reason))
        job.processed = i + 1
        if (i + 1) % 25 == 0:
            session.commit()
    scored.sort(reverse=True)
    fswriter.write_bad_labels(dataset, [f"{s} {sc:.4f} {r}" for sc, s, r in scored])
    bad = {s for _, s, _ in scored}
    for row in session.query(Image).all():
        row.in_bad_labels = row.stem in bad
    job.result = {"flagged": len(scored)}
    session.commit()


def _xyxy_to_cxcywh(b):
    x1, y1, x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
    return ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)


def run_dedup(session, cfg, job, params):
    dataset = Path(cfg.dataset_dir)
    pool = params.get("pool", "all")
    thresh = float(params.get("thresh", 3.0))
    hs = int(params.get("hash", 32))
    stems = image_stems(dataset)
    if pool in ("model", "bad"):
        listfile = {"model": "model_labeled.txt", "bad": "bad_labels.txt"}[pool]
        keep = read_stem_list(dataset / listfile)
        stems = [s for s in stems if s in keep]
    job.total = len(stems)
    session.commit()
    sigs, valid = [], []
    for i, stem in enumerate(stems):
        sig = dedup.signature(dataset / "images" / f"{stem}.jpg", hs)
        if sig is not None:
            sigs.append(sig); valid.append(stem)
        job.processed = i + 1
        if (i + 1) % 200 == 0:
            session.commit()
    for ref_i, dup_i, d in dedup.find_duplicates(sigs, thresh):
        session.add(DedupPair(keeper_stem=valid[ref_i], dup_stem=valid[dup_i], diff=d, pool=pool, status="todo"))
    job.result = {"pairs": session.query(DedupPair).count()}
    session.commit()


def run_job(session, cfg, job):
    job.status = "running"
    session.commit()
    try:
        if job.type == "oracle":
            run_oracle(session, cfg, job, job.params)
        elif job.type == "dedup":
            run_dedup(session, cfg, job, job.params)
        else:
            raise ValueError(f"unknown job type: {job.type}")
        job.status = "done"
    except Exception as e:
        job.status = "error"
        job.message = str(e)[:500]
    session.commit()


def worker_once(session_factory, cfg):
    session = session_factory()
    try:
        job = session.execute(
            select(Job).where(Job.status == "queued").order_by(Job.id)
            .with_for_update(skip_locked=True).limit(1)
        ).scalars().first()
        if job is None:
            return None
        run_job(session, cfg, job)
        return job.id
    finally:
        session.close()
