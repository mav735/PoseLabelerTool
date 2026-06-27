import datetime
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from app.deps import get_config, get_engine, get_session
from app.models import create_all, Lease
from app.dataset import scan
from app import leasing, actions, users, fswriter
from app.payloads import label_payload
from app.schemas import LoginReq, LeaseReq, HeartbeatReq, SubmitReq, ReleaseReq


class _StemReq(BaseModel):
    stem: str


class _PurgeReq(BaseModel):
    stem: str | None = None


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


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
        if not stem.isdigit():
            raise HTTPException(status_code=400, detail="bad stem")
        p = Path(get_config().dataset_dir) / "images" / f"{stem}.jpg"
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type="image/jpeg")

    @app.get("/api/label/{stem}")
    def get_label(stem: str):
        if not stem.isdigit():
            raise HTTPException(status_code=400, detail="bad stem")
        return label_payload(get_config().dataset_dir, stem)

    @app.get("/api/trash")
    def trash_list():
        return {"stems": fswriter.list_trash(get_config().dataset_dir)}

    @app.post("/api/trash/restore")
    def trash_restore(body: _StemReq):
        return {"ok": fswriter.restore_from_trash(get_config().dataset_dir, body.stem)}

    @app.post("/api/trash/purge")
    def trash_purge(body: _PurgeReq):
        return {"purged": fswriter.purge_trash(get_config().dataset_dir, body.stem)}

    return app


app = create_app()
