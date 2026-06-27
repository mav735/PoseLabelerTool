from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from app.deps import get_config, get_engine, get_session
from app.models import create_all
from app.dataset import scan


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        create_all(get_engine())
        yield

    app = FastAPI(title="Pose Labeler", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/scan")
    def run_scan(session=Depends(get_session)):
        cfg = get_config()
        return scan(session, Path(cfg.dataset_dir))

    return app


app = create_app()
