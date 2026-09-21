import datetime
import hashlib
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect, select, text as sa_text
from app.deps import get_config, get_engine, get_session
from app.models import Lease, PredCache, Job, Image, DedupPair
from app.dataset import scan
from app.datasets_mgr import safe_dataset_path, is_ready
from app.dataset_paths import image_path
from app import datasets_mgr, leasing, actions, users, fswriter, inference, jobs as jobs_mod
from app.catalog import load_catalog_safe, add_dataset, DatasetEntry, CatalogError
from app.models_fs import list_models, safe_model_path
from app.payloads import label_payload
from app.schemas import (LoginReq, LeaseReq, HeartbeatReq, SubmitReq, ReleaseReq,
                         StemReq, PurgeReq, JobReq, DedupNextReq, DedupResolveReq)


class _AddDatasetReq(BaseModel):
    name: str
    repo: str | None = None
    revision: str = "main"


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dataset_dir(name: str) -> Path:
    cfg = get_config()
    try:
        path = safe_dataset_path(cfg.datasets_root, name)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad dataset")
    if not is_ready(path):
        raise HTTPException(status_code=404, detail="dataset not ready")
    return path


def _shard_for(session, dataset: str, stem: str) -> str:
    """Resolve a stem's shard from the database.

    The shard is never accepted from the client: the dataset name is already
    one client-supplied path component, and a second would double the surface.
    """
    row = session.get(Image, (dataset, stem))
    if row is None:
        raise HTTPException(status_code=404, detail="unknown image")
    return row.shard


def _scan_lock_key(dataset: str) -> int:
    """A stable signed 64-bit advisory-lock key for a dataset name."""
    return int.from_bytes(
        hashlib.blake2b(dataset.encode(), digest_size=8).digest(),
        "big", signed=True)


def _ensure_scanned(session, dataset: str, ds_dir: Path) -> None:
    """Scan on first use. Boot no longer knows which dataset to scan.

    FastAPI runs non-async endpoints on a threadpool, so several requests for a
    never-scanned dataset arrive concurrently on independent sessions. Without
    serialisation they all see an empty table, all call scan(), and the losers
    die on the images primary key with a UniqueViolation.

    A transaction-scoped Postgres advisory lock keyed on the dataset name fixes
    that: exactly one caller scans, and the others block until it commits (the
    lock is released by that commit) and then re-check and find the rows. The
    alternative -- catching IntegrityError and retrying -- would leave the
    losers on an exception path with a rolled-back session; here they simply
    return, having seen the scanned rows, which is what the caller needs.
    """
    if session.query(Image).filter(Image.dataset == dataset).first() is not None:
        return
    session.execute(sa_text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": _scan_lock_key(dataset)})
    # Re-check under the lock: a concurrent caller may have scanned while we
    # waited. READ COMMITTED gives this statement a fresh snapshot.
    if session.query(Image).filter(Image.dataset == dataset).first() is not None:
        return
    scan(session, dataset, ds_dir)


def _migrate_to_head() -> None:
    """Bring the database schema to head.

    Four cases, because a database built by ``create_all`` carries no
    ``alembic_version`` and so cannot say for itself how far along it is:

    * already under Alembic  -> upgrade from wherever it is.
    * ``images.dataset`` present -> ``create_all`` against the current models
      (the test suite does this); the schema is already at head, so stamp it.
    * ``users`` but no ``images.dataset`` -> a legacy single-dataset install,
      built by the ``create_all`` that used to run at boot. It is at 0001, so
      stamp it there and let 0002 run and backfill.
    * nothing at all -> upgrade from scratch.
    """
    from alembic import command
    from alembic.config import Config as AlembicConfig
    cfg = get_config()
    acfg = AlembicConfig(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    acfg.set_main_option("sqlalchemy.url", cfg.db_url)
    # 0002 reads the backfill dataset name from the environment, because a
    # migration has no access to the Config object. Hand it the configured
    # value -- setdefault, so an explicitly-set env var still wins, which is
    # the same precedence load_config applies.
    os.environ.setdefault("PLT_MIGRATE_DEFAULT_DATASET", cfg.migrate_default_dataset)
    insp = sa_inspect(get_engine())
    tables = set(insp.get_table_names())
    columns = ({c["name"] for c in insp.get_columns("images")}
               if "images" in tables else set())
    if "alembic_version" in tables:
        command.upgrade(acfg, "head")
    elif "dataset" in columns:
        command.stamp(acfg, "head")
    elif "users" in tables:
        command.stamp(acfg, "0001_baseline")
        command.upgrade(acfg, "head")
    else:
        command.upgrade(acfg, "head")


def _lease_payload(session, cfg, dataset, task, user_id):
    stem = leasing.acquire(session, dataset, task, user_id, now_utc(), cfg.lease_timeout)
    if stem is None:
        return None
    lease = session.execute(select(Lease).where(
        Lease.dataset == dataset, Lease.stem == stem, Lease.task == task,
        Lease.user_id == user_id, Lease.released_at.is_(None))).scalars().first()
    payload = label_payload(safe_dataset_path(cfg.datasets_root, dataset),
                            _shard_for(session, dataset, stem), stem)
    payload["lease_id"] = lease.id
    return payload


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _migrate_to_head()
        cfg = get_config()
        stop = threading.Event()

        def _sweeper():
            from app import deps
            while not stop.wait(cfg.heartbeat_interval):
                try:
                    deps.get_engine()
                    s = deps._session_factory()
                    try:
                        leasing.sweep_expired(s, now_utc())
                    finally:
                        s.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_sweeper, daemon=True)
        thread.start()

        from app import deps as _deps
        s0 = _deps._session_factory()
        try:
            for j in s0.query(Job).filter(Job.status == "running").all():
                j.status = "queued"
            s0.commit()
        finally:
            s0.close()

        def _worker(lane):
            from app import deps as d
            while not stop.wait(2.0):
                try:
                    jobs_mod.worker_once(d._session_factory, cfg, lane=lane)
                except Exception:
                    pass

        threads = [threading.Thread(target=_worker, args=(lane,), daemon=True)
                   for lane in ("compute", "transfer")]
        for t in threads:
            t.start()
        yield
        stop.set()

    app = FastAPI(title="Pose Labeler", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/datasets")
    def datasets_list():
        from app.hf.client import token_from_env
        cfg = get_config()
        cat, err = load_catalog_safe(cfg.catalog_path)
        rows = datasets_mgr.list_status(cfg.datasets_root, cat,
                                        token_present=token_from_env() is not None)
        if err:
            for row in rows:
                row["catalog_error"] = err
        return rows

    @app.get("/api/datasets/{name}")
    def dataset_get(name: str):
        from app.hf.client import token_from_env
        cfg = get_config()
        cat, err = load_catalog_safe(cfg.catalog_path)
        for row in datasets_mgr.list_status(cfg.datasets_root, cat,
                                            token_present=token_from_env() is not None):
            if row["name"] == name:
                if err:
                    row["catalog_error"] = err
                return row
        raise HTTPException(status_code=404, detail="unknown dataset")

    @app.post("/api/datasets/{name}/download")
    def dataset_download(name: str, session=Depends(get_session)):
        cfg = get_config()
        try:
            safe_dataset_path(cfg.datasets_root, name)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad dataset name")
        cat, _ = load_catalog_safe(cfg.catalog_path)
        entry = next((d for d in cat.datasets if d.name == name), None)
        if entry is None:
            raise HTTPException(status_code=404, detail="unknown dataset")
        if not entry.repo:
            raise HTTPException(status_code=400, detail="dataset is local-only")
        running = session.execute(
            select(Job).where(Job.dataset == name, Job.type == "download",
                              Job.status.in_(("queued", "running")))
        ).scalars().first()
        if running is not None:
            raise HTTPException(status_code=409, detail="a download is already running")
        job = Job(dataset=name, type="download", params={}, status="queued")
        session.add(job); session.commit()
        return {"job_id": job.id}

    @app.post("/api/models/{name}/download")
    def model_download(name: str, session=Depends(get_session)):
        cfg = get_config()
        cat, _ = load_catalog_safe(cfg.catalog_path)
        entry = next((m for m in cat.models if m.name == name), None)
        if entry is None:
            raise HTTPException(status_code=404, detail="unknown model")
        if not entry.repo or not entry.file:
            raise HTTPException(status_code=400, detail="model has no repo or file")
        running = session.execute(
            select(Job).where(Job.type == "model_download",
                              Job.status.in_(("queued", "running")),
                              Job.params["model"].astext == name)
        ).scalars().first()
        if running is not None:
            raise HTTPException(status_code=409, detail="a download is already running")
        job = Job(dataset="", type="model_download", params={"model": name},
                  status="queued")
        session.add(job); session.commit()
        return {"job_id": job.id}

    @app.post("/api/datasets")
    def dataset_add(body: _AddDatasetReq):
        cfg = get_config()
        try:
            safe_dataset_path(cfg.datasets_root, body.name)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad dataset name")
        try:
            add_dataset(cfg.catalog_path,
                       DatasetEntry(name=body.name, repo=body.repo,
                                    revision=body.revision))
        except CatalogError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"ok": True}

    @app.post("/api/scan")
    def run_scan(dataset: str, session=Depends(get_session)):
        return scan(session, dataset, _dataset_dir(dataset))

    @app.post("/api/login")
    def login(body: LoginReq, session=Depends(get_session)):
        user = users.get_or_create_user(session, body.username)
        return {"user_id": user.id, "username": user.username}

    @app.post("/api/lease")
    def lease(body: LeaseReq, session=Depends(get_session)):
        ds_dir = _dataset_dir(body.dataset)
        _ensure_scanned(session, body.dataset, ds_dir)
        payload = _lease_payload(session, get_config(), body.dataset, body.task,
                                 body.user_id)
        return payload if payload else {"stem": None}

    @app.post("/api/heartbeat")
    def heartbeat(body: HeartbeatReq, session=Depends(get_session)):
        ok = leasing.heartbeat(session, body.lease_id, now_utc(), get_config().lease_timeout)
        return {"ok": ok}

    @app.post("/api/submit")
    def submit(body: SubmitReq, session=Depends(get_session)):
        cfg = get_config()
        ds_dir = _dataset_dir(body.dataset)
        try:
            actions.apply_action(session, body.dataset, ds_dir, body.stem, body.task,
                                 body.user_id, body.action, body.instances,
                                 body.width, body.height)
        except actions.UnknownImage:
            raise HTTPException(status_code=404, detail="unknown image")
        leasing.release_active(session, body.dataset, body.user_id, body.stem,
                               body.task, now_utc())
        payload = _lease_payload(session, cfg, body.dataset, body.task, body.user_id)
        return {"next": payload}

    @app.post("/api/release")
    def release(body: ReleaseReq, session=Depends(get_session)):
        return {"ok": leasing.release(session, body.lease_id, now_utc())}

    @app.get("/api/image/{stem}")
    def get_image(stem: str, dataset: str, session=Depends(get_session)):
        if not fswriter.is_valid_stem(stem):
            raise HTTPException(status_code=400, detail="bad stem")
        ds_dir = _dataset_dir(dataset)
        p = image_path(ds_dir, _shard_for(session, dataset, stem), stem)
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type="image/jpeg")

    @app.get("/api/label/{stem}")
    def get_label(stem: str, dataset: str, session=Depends(get_session)):
        if not fswriter.is_valid_stem(stem):
            raise HTTPException(status_code=400, detail="bad stem")
        return label_payload(_dataset_dir(dataset),
                             _shard_for(session, dataset, stem), stem)

    @app.get("/api/models")
    def models_list():
        return list_models(get_config().models_root)

    @app.get("/api/pred/{stem}")
    def get_pred(stem: str, dataset: str, model: str, session=Depends(get_session)):
        if not fswriter.is_valid_stem(stem):
            raise HTTPException(status_code=400, detail="bad stem")
        cfg = get_config()
        ds_dir = _dataset_dir(dataset)
        try:
            model_path = safe_model_path(cfg.models_root, model)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad model path")
        cached = session.get(PredCache, (dataset, stem, model))
        if cached:
            return cached.preds["instances"]
        img = image_path(ds_dir, _shard_for(session, dataset, stem), stem)
        if not img.exists():
            raise HTTPException(status_code=404, detail="image not found")
        m = inference.load_model(str(model_path))
        instances = inference.pred_to_instances(inference.run_pred(m, str(img)))
        session.add(PredCache(dataset=dataset, stem=stem, model_key=model,
                              preds={"instances": instances}))
        session.commit()
        return instances

    @app.get("/api/stats")
    def get_stats(dataset: str, task: str, session=Depends(get_session)):
        if task not in leasing.TASKS:
            raise HTTPException(status_code=400, detail="unknown task")
        ds_dir = _dataset_dir(dataset)
        _ensure_scanned(session, dataset, ds_dir)
        return leasing.task_stats(session, dataset, task)

    @app.get("/api/trash")
    def trash_list(dataset: str):
        return {"stems": fswriter.list_trash(_dataset_dir(dataset))}

    @app.post("/api/trash/restore")
    def trash_restore(body: StemReq, session=Depends(get_session)):
        ds_dir = _dataset_dir(body.dataset)
        shard = _shard_for(session, body.dataset, body.stem)
        return {"ok": fswriter.restore_from_trash(ds_dir, shard, body.stem)}

    @app.post("/api/trash/purge")
    def trash_purge(body: PurgeReq, session=Depends(get_session)):
        ds_dir = _dataset_dir(body.dataset)
        if body.stem is None:
            return {"purged": fswriter.purge_trash(ds_dir)}
        shard = _shard_for(session, body.dataset, body.stem)
        return {"purged": fswriter.purge_trash(ds_dir, shard=shard, stem=body.stem)}

    @app.post("/api/jobs")
    def start_job(body: JobReq, session=Depends(get_session)):
        if body.type not in ("oracle", "dedup"):
            raise HTTPException(status_code=400, detail="bad job type")
        _dataset_dir(body.dataset)
        if body.type == "oracle":
            try:
                safe_model_path(get_config().models_root, str(body.params.get("model", "")))
            except ValueError:
                raise HTTPException(status_code=400, detail="bad model path")
        job = Job(dataset=body.dataset, type=body.type, params=body.params,
                  status="queued")
        session.add(job); session.commit()
        return {"id": job.id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: int, session=Depends(get_session)):
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404)
        return {"id": job.id, "type": job.type, "status": job.status,
                "processed": job.processed, "total": job.total, "message": job.message,
                "result": job.result, "meta": job.meta}

    @app.get("/api/jobs")
    def jobs_list(session=Depends(get_session)):
        rows = session.query(Job).order_by(Job.id.desc()).limit(20).all()
        return [{"id": j.id, "dataset": j.dataset, "type": j.type, "status": j.status,
                 "processed": j.processed, "total": j.total} for j in rows]

    @app.post("/api/dedup/next")
    def dedup_next(body: DedupNextReq, session=Depends(get_session)):
        ds_dir = _dataset_dir(body.dataset)
        # The UI can reach dedup review without ever calling /api/lease or
        # /api/stats, and the image endpoints now resolve the shard from the
        # Image row. Scan here too, or the keeper and the duplicate both 404.
        _ensure_scanned(session, body.dataset, ds_dir)
        pair = session.execute(
            select(DedupPair).where(DedupPair.dataset == body.dataset,
                                    DedupPair.status == "todo").order_by(DedupPair.id)
            .with_for_update(skip_locked=True).limit(1)
        ).scalars().first()
        if pair is None:
            return {"id": None}
        pair.status = "leased"; pair.user_id = body.user_id
        session.commit()
        return {"id": pair.id, "keeper": pair.keeper_stem, "dup": pair.dup_stem, "diff": pair.diff}

    @app.post("/api/dedup/resolve")
    def dedup_resolve(body: DedupResolveReq, session=Depends(get_session)):
        pair = session.get(DedupPair, body.pair_id)
        if not pair:
            raise HTTPException(status_code=404)
        if pair.status != "leased":
            raise HTTPException(status_code=409, detail="pair not leased")
        if body.action == "delete":
            ds_dir = _dataset_dir(pair.dataset)
            img = session.get(Image, (pair.dataset, pair.dup_stem))
            shard = img.shard if img is not None else ""
            if not fswriter.move_to_trash(ds_dir, shard, pair.dup_stem):
                # Nothing moved: the image is not where the shard says it is.
                # Marking the pair done here would tell the operator the
                # duplicate was deleted, drop it out of the queue forever, and
                # leave the file on disk.
                raise HTTPException(status_code=404,
                                    detail="duplicate image not found")
            fswriter.prune_from_lists(ds_dir, pair.dup_stem)
            if img:
                img.deleted = True
        pair.status = "done"; pair.action = body.action
        session.commit()
        return {"ok": True}

    return app


app = create_app()
