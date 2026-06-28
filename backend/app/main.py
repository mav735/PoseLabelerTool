import datetime
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from app.deps import get_config, get_engine, get_session
from app.models import create_all, Lease, PredCache, Job, Image, DedupPair, User
from app.dataset import scan
from app import leasing, actions, users, fswriter, inference, jobs as jobs_mod
from app.models_fs import list_models
from app.payloads import label_payload
from app.schemas import LoginReq, LeaseReq, HeartbeatReq, SubmitReq, ReleaseReq


class _StemReq(BaseModel):
    stem: str


class _PurgeReq(BaseModel):
    stem: str | None = None


class _JobReq(BaseModel):
    type: str
    params: dict = {}


class _DedupNextReq(BaseModel):
    user_id: int


class _DedupResolveReq(BaseModel):
    pair_id: int
    action: Literal["delete", "keep"]


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def maybe_initial_scan(session, cfg) -> int:
    from app.models import Image
    if session.query(Image).first() is not None:
        return 0
    counts = scan(session, Path(cfg.dataset_dir))
    return counts["scanned"]


def _lease_payload(session, cfg, task, user_id):
    stem = leasing.acquire(session, task, user_id, now_utc(), cfg.lease_timeout)
    if stem is None:
        return None
    lease = session.execute(select(Lease).where(
        Lease.stem == stem, Lease.task == task, Lease.user_id == user_id,
        Lease.released_at.is_(None))).scalars().first()
    payload = label_payload(cfg.dataset_dir, stem)
    payload["lease_id"] = lease.id
    return payload


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        create_all(get_engine())
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

        from app import deps as _d
        s1 = _d._session_factory()
        try:
            maybe_initial_scan(s1, cfg)
        except Exception:
            pass
        finally:
            s1.close()

        def _worker():
            from app import deps as d
            while not stop.wait(2.0):
                try:
                    jobs_mod.worker_once(d._session_factory, cfg)
                except Exception:
                    pass
        wt = threading.Thread(target=_worker, daemon=True)
        wt.start()
        yield
        stop.set()

    app = FastAPI(title="Pose Labeler", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/scan")
    def run_scan(session=Depends(get_session)):
        return scan(session, Path(get_config().dataset_dir))

    @app.post("/api/login")
    def login(body: LoginReq, session=Depends(get_session)):
        user = users.get_or_create_user(session, body.username)
        return {"user_id": user.id, "username": user.username}

    @app.post("/api/lease")
    def lease(body: LeaseReq, session=Depends(get_session)):
        payload = _lease_payload(session, get_config(), body.task, body.user_id)
        return payload if payload else {"stem": None}

    @app.post("/api/heartbeat")
    def heartbeat(body: HeartbeatReq, session=Depends(get_session)):
        ok = leasing.heartbeat(session, body.lease_id, now_utc(), get_config().lease_timeout)
        return {"ok": ok}

    @app.post("/api/submit")
    def submit(body: SubmitReq, session=Depends(get_session)):
        cfg = get_config()
        actions.apply_action(session, Path(cfg.dataset_dir), body.stem, body.task,
                             body.user_id, body.action, body.instances,
                             body.width, body.height)
        leasing.release_active(session, body.user_id, body.stem, body.task, now_utc())
        payload = _lease_payload(session, cfg, body.task, body.user_id)
        return {"next": payload}

    @app.post("/api/release")
    def release(body: ReleaseReq, session=Depends(get_session)):
        return {"ok": leasing.release(session, body.lease_id, now_utc())}

    @app.get("/api/image/{stem}")
    def get_image(stem: str):
        if not fswriter.is_valid_stem(stem):
            raise HTTPException(status_code=400, detail="bad stem")
        p = Path(get_config().dataset_dir) / "images" / f"{stem}.jpg"
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type="image/jpeg")

    @app.get("/api/label/{stem}")
    def get_label(stem: str):
        if not fswriter.is_valid_stem(stem):
            raise HTTPException(status_code=400, detail="bad stem")
        return label_payload(get_config().dataset_dir, stem)

    @app.get("/api/models")
    def models_list():
        return list_models(get_config().models_dir)

    @app.get("/api/pred/{stem}")
    def get_pred(stem: str, model: str, session=Depends(get_session)):
        if not fswriter.is_valid_stem(stem):
            raise HTTPException(status_code=400, detail="bad stem")
        cfg = get_config()
        from app.models_fs import safe_model_path
        try:
            model_path = safe_model_path(cfg.models_dir, model)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad model path")
        cached = session.get(PredCache, (stem, model))
        if cached:
            return cached.preds["instances"]
        img = Path(cfg.dataset_dir) / "images" / f"{stem}.jpg"
        if not img.exists():
            raise HTTPException(status_code=404, detail="image not found")
        m = inference.load_model(str(model_path))
        instances = inference.pred_to_instances(inference.run_pred(m, str(img)))
        session.add(PredCache(stem=stem, model_key=model, preds={"instances": instances}))
        session.commit()
        return instances

    @app.get("/api/stats")
    def get_stats(task: str, session=Depends(get_session)):
        if task not in leasing.TASKS:
            raise HTTPException(status_code=400, detail="unknown task")
        return leasing.task_stats(session, task)

    @app.get("/api/trash")
    def trash_list():
        return {"stems": fswriter.list_trash(get_config().dataset_dir)}

    @app.post("/api/trash/restore")
    def trash_restore(body: _StemReq):
        return {"ok": fswriter.restore_from_trash(get_config().dataset_dir, body.stem)}

    @app.post("/api/trash/purge")
    def trash_purge(body: _PurgeReq):
        return {"purged": fswriter.purge_trash(get_config().dataset_dir, body.stem)}

    @app.post("/api/jobs")
    def start_job(body: _JobReq, session=Depends(get_session)):
        if body.type not in ("oracle", "dedup"):
            raise HTTPException(status_code=400, detail="bad job type")
        if body.type == "oracle":
            from app.models_fs import safe_model_path
            try:
                safe_model_path(get_config().models_dir, str(body.params.get("model", "")))
            except ValueError:
                raise HTTPException(status_code=400, detail="bad model path")
        job = Job(type=body.type, params=body.params, status="queued")
        session.add(job); session.commit()
        return {"id": job.id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: int, session=Depends(get_session)):
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404)
        return {"id": job.id, "type": job.type, "status": job.status,
                "processed": job.processed, "total": job.total, "message": job.message, "result": job.result}

    @app.get("/api/jobs")
    def jobs_list(session=Depends(get_session)):
        rows = session.query(Job).order_by(Job.id.desc()).limit(20).all()
        return [{"id": j.id, "type": j.type, "status": j.status, "processed": j.processed, "total": j.total} for j in rows]

    @app.post("/api/dedup/next")
    def dedup_next(body: _DedupNextReq, session=Depends(get_session)):
        pair = session.execute(
            select(DedupPair).where(DedupPair.status == "todo").order_by(DedupPair.id)
            .with_for_update(skip_locked=True).limit(1)
        ).scalars().first()
        if pair is None:
            return {"id": None}
        pair.status = "leased"; pair.user_id = body.user_id
        session.commit()
        return {"id": pair.id, "keeper": pair.keeper_stem, "dup": pair.dup_stem, "diff": pair.diff}

    @app.post("/api/dedup/resolve")
    def dedup_resolve(body: _DedupResolveReq, session=Depends(get_session)):
        pair = session.get(DedupPair, body.pair_id)
        if not pair:
            raise HTTPException(status_code=404)
        if pair.status != "leased":
            raise HTTPException(status_code=409, detail="pair not leased")
        cfg = get_config()
        if body.action == "delete":
            fswriter.move_to_trash(cfg.dataset_dir, pair.dup_stem)
            fswriter.prune_from_lists(cfg.dataset_dir, pair.dup_stem)
            img = session.get(Image, pair.dup_stem)
            if img:
                img.deleted = True
        pair.status = "done"; pair.action = body.action
        session.commit()
        return {"ok": True}

    return app


app = create_app()
