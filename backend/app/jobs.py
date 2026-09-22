from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy import select
from app import inference, oracle, dedup, fswriter
from app.labels import parse_label
from app.dataset import read_stem_list
from app.dataset_paths import iter_image_files, image_path, label_path
from app.datasets_mgr import safe_dataset_path, is_ready
from app.models import Image, Job, DedupPair
from app.models_fs import safe_model_path


def _ordered_images(ds_dir) -> list:
    """(shard, stem) for every image, in the order image_stems has always used.

    Numeric stems sort numerically, not lexicographically ("9" before "100").
    find_duplicates returns index pairs into this order, so the order decides
    which member of a duplicate pair is the keeper and which is the one the
    operator is offered for deletion.
    """
    return sorted(iter_image_files(ds_dir),
                  key=lambda p: (p[0], (0, int(p[1])) if p[1].isdigit() else (1, p[1])))


def _num(params, key, default, cast=float):
    v = params.get(key)
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def _gt_pixels(text, w, h):
    out = []
    for inst in parse_label(text):
        out.append({
            "bbox": (inst.cx * w, inst.cy * h, inst.w * w, inst.h * h),
            "kpts": [(k.x * w, k.y * h, k.v) for k in inst.kpts],
        })
    return out


def run_oracle(session, cfg, job, params):
    dataset = job.dataset
    ds_dir = safe_dataset_path(cfg.datasets_root, dataset)
    approved = read_stem_list(ds_dir / "reviewed_keep.txt")
    pairs = [(sh, st) for sh, st in _ordered_images(ds_dir) if st not in approved]
    model = inference.load_model(str(safe_model_path(cfg.models_root, params["model"])))
    mode = params.get("mode", "a")
    thr = _num(params, "threshold", 0.3)
    job.total = len(pairs)
    session.commit()
    scored = []
    skipped = 0
    for i, (shard, stem) in enumerate(pairs):
        job.processed = i + 1
        try:
            img = image_path(ds_dir, shard, stem)
            lbl = label_path(ds_dir, shard, stem)
            with PILImage.open(img) as im:
                w, h = im.width, im.height
            gt = _gt_pixels(lbl.read_text() if lbl.exists() else "", w, h)
            raw = inference.run_pred(model, str(img))
            preds = [{"bbox": _xyxy_to_cxcywh(b), "conf": c,
                      "kpts": [(float(k[0]), float(k[1]), float(k[2])) for k in kp]} for b, c, kp in raw]
            sc, reason = oracle.score_image_b(gt, preds) if mode == "b" else oracle.score_image_a(gt, preds)
            if sc >= thr:
                scored.append((sc, stem, reason))
        except Exception:
            skipped += 1
        if (i + 1) % 25 == 0:
            session.commit()
    scored.sort(reverse=True)
    fswriter.write_bad_labels(ds_dir, [f"{s} {sc:.4f} {r}" for sc, s, r in scored])
    bad = {s for _, s, _ in scored}
    for row in session.query(Image).filter(Image.dataset == dataset).all():
        row.in_bad_labels = row.stem in bad
    job.result = {"flagged": len(scored), "skipped": skipped}
    session.commit()


def _xyxy_to_cxcywh(b):
    x1, y1, x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
    return ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)


def run_dedup(session, cfg, job, params):
    dataset = job.dataset
    ds_dir = safe_dataset_path(cfg.datasets_root, dataset)
    pool = params.get("pool", "all")
    thresh = _num(params, "thresh", 3.0)
    hs = _num(params, "hash", 32, int)
    pairs = _ordered_images(ds_dir)
    if pool in ("model", "bad"):
        listfile = {"model": "model_labeled.txt", "bad": "bad_labels.txt"}[pool]
        keep = read_stem_list(ds_dir / listfile)
        pairs = [(sh, st) for sh, st in pairs if st in keep]
    job.total = len(pairs)
    session.commit()
    sigs, valid = [], []
    for i, (shard, stem) in enumerate(pairs):
        sig = dedup.signature(image_path(ds_dir, shard, stem), hs)
        if sig is not None:
            sigs.append(sig); valid.append(stem)
        job.processed = i + 1
        if (i + 1) % 200 == 0:
            session.commit()
    session.query(DedupPair).filter(
        DedupPair.dataset == dataset, DedupPair.pool == pool,
        DedupPair.status == "todo").delete()
    dups = dedup.find_duplicates(sigs, thresh)
    for ref_i, dup_i, d in dups:
        session.add(DedupPair(dataset=dataset, keeper_stem=valid[ref_i],
                              dup_stem=valid[dup_i], diff=d, pool=pool, status="todo"))
    job.result = {"pairs": len(dups)}
    session.commit()


TRANSFER_TYPES = ("download", "model_download", "sync")
COMPUTE_TYPES = ("oracle", "dedup")


def run_job(session, cfg, job, client=None):
    job.status = "running"
    session.commit()
    try:
        if job.type in TRANSFER_TYPES:
            # No readiness guard here. A download runs precisely because the
            # dataset is NOT ready; requiring readiness would deadlock it.
            from app.hf.client import make_client
            from app.hf.download import run_download
            from app.hf.sync import run_sync
            c = client if client is not None else make_client()
            if job.type == "download":
                run_download(session, cfg, job, c)
            elif job.type == "sync":
                run_sync(session, cfg, job, c)
            else:
                run_model_download(session, cfg, job, job.params, c)
        else:
            # safe_dataset_path only validates the name; it does not check
            # that the directory is actually ready, unlike the API's
            # _dataset_dir. If the dataset's directory disappeared between
            # the job being queued and run, image_stems would silently glob
            # an empty/missing dir and the oracle would write an empty
            # bad_labels.txt, clearing every flag. Fail loudly instead.
            if not is_ready(safe_dataset_path(cfg.datasets_root, job.dataset)):
                raise ValueError(f"dataset not ready: {job.dataset!r}")
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


def run_model_download(session, cfg, job, params, client) -> None:
    """Fetch one model file into models_root."""
    from app.catalog import load_catalog
    from app.hf.download import ProgressSink
    name = params.get("model", "")
    cat = load_catalog(cfg.catalog_path)
    entry = next((m for m in cat.models if m.name == name), None)
    if entry is None:
        raise ValueError(f"model not in catalog: {name!r}")
    if not entry.repo or not entry.file:
        raise ValueError(f"model has no repo or file: {name!r}")
    dest = Path(cfg.models_root)
    dest.mkdir(parents=True, exist_ok=True)
    # file_size, NOT repo_size: a model repo may hold several checkpoints and
    # we fetch exactly one, so the repo total would stall the bar partway.
    sink = ProgressSink(session, job, client.file_size(entry.repo, entry.file))
    try:
        client.fetch_file(entry.repo, entry.file, dest, on_bytes=sink.add)
    finally:
        sink.flush()
    job.result = {"file": entry.file, "bytes": job.processed}
    session.commit()


def worker_once(session_factory, cfg, lane: str = "compute"):
    types = TRANSFER_TYPES if lane == "transfer" else COMPUTE_TYPES
    session = session_factory()
    try:
        job = session.execute(
            select(Job).where(Job.status == "queued", Job.type.in_(types))
            .order_by(Job.id).with_for_update(skip_locked=True).limit(1)
        ).scalars().first()
        if job is None:
            return None
        run_job(session, cfg, job)
        return job.id
    finally:
        session.close()
