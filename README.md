# Pose Labeler Tool

A fast, single-purpose web app for reviewing and fixing model-generated 15-keypoint
YOLO-pose labels — multi-user, on a LAN. Replaces the `review_bad.py` / `dedup.py` /
`find_bad_labels.py` CLIs with a browser UI.

## Quick start

1. Install Docker (with the NVIDIA Container Toolkit if you want GPU inference).
2. Copy the config and point it at your datasets + models:
   ```
   cp .env.example .env
   # edit .env: DATASETS_ROOT, MODELS_DIR, APP_PORT
   # point MODELS_DIR at a directory of .pt files; it is shared across datasets
   ```
3. Check the port is free, then launch:
   ```
   python scripts/preflight.py
   docker compose up --build            # CPU
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build   # GPU
   ```
4. Open `http://localhost:8080` (or your `APP_PORT`), enter a username, pick a model
   and a task, and click Review.

The backend auto-scans a dataset into the database the first time it is leased from. To
re-scan after adding images, POST `/api/scan`.

## Config (`.env`)

| key | meaning |
|-----|---------|
| `DATASETS_ROOT` | host path to the *parent* directory holding one folder per dataset (each with its own `images/`, `labels/`, the list files) — mounted read-write |
| `MODELS_DIR` | host path to a directory of `.pt` model files, shared across all datasets — mounted read-write |
| `APP_PORT` | the single published host port (frontend) |

Postgres runs internally on the compose network and is never published. Data persists
in the `pgdata` volume.

An existing single-dataset database is migrated automatically at backend startup; its
rows are backfilled into a dataset named by `MIGRATE_DEFAULT_DATASET` (default
`"default"`). Set that variable in `.env` before first boot against an old database if
you want a better name for the upgraded dataset — under `docker compose` it is passed
into the container as `PLT_MIGRATE_DEFAULT_DATASET`; if you run the backend directly
without compose, set `PLT_MIGRATE_DEFAULT_DATASET` itself instead.

## Datasets

`datasets.yaml` (see `backend/datasets.example.yaml` for the format) is the catalog: it
lists known datasets and models, optionally with a `repo:` for ones fetchable from a
remote. Under `docker compose`, it lives at `DATASETS_ROOT/datasets.yaml` — inside the
mounted volume, so entries added through the UI's "+ Add repo" button survive a restart.
A folder dropped straight into `DATASETS_ROOT` is discovered automatically and shows up
in the setup screen even with no catalog entry. An entry in the catalog with no `repo:`
is local-only — it is expected to already exist under `DATASETS_ROOT` and is not fetched
from anywhere.

## GPU vs CPU

- GPU: needs the NVIDIA Container Toolkit + the `docker-compose.gpu.yml` override. The
  image installs CUDA 12.8 torch wheels (Blackwell / RTX 50-series). The code
  auto-detects the GPU.
- CPU only: omit the GPU override and build the backend with the CPU torch index:
  `docker compose build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu`.
  Inference still works (slower; the oracle over a large dataset takes a while).

## Tasks & tools

- **Review** bad / model / all — lease an image, keep / drop / clear / edit (canvas editor:
  drag keypoints, click-to-place add, right-click visibility, drag a predicted instance
  into Truth). PRED overlay (`v` to toggle) needs a model selected.
- **Tools** — run the oracle (flags bad labels into the "Review bad" task) and dedup
  (finds near-duplicate frames) as background jobs with progress.
- **Dedup** — review near-duplicate pairs side by side; delete (soft, to the dataset's
  `.trash/`) or keep.

## Keyboard (review + editor)

- Review: `k` keep · `d` drop · `c` clear · `e` edit · `v`/←/→ view (GT / PRED / Clear) · `h` names · wheel zoom · drag pan · `0` reset.
- Editor: drag keypoint · drag inside box = move instance · right-click = cycle visibility · `n` click-to-place add (head→torso→legs→arms) · `s` skip bone · `x` delete · `ENTER` save · `ESC` cancel.

## Notes

- The backend runs a single uvicorn worker by design (serialized filesystem writes + a
  single GPU job worker). Do not scale it with `--workers`.
- Drops and dedup-deletes are soft (moved to each dataset's `.trash/`), not unlinked.
- Stems are integer-sortable timestamp strings; the label format is YOLO-pose
  (`0 cx cy w h x1 y1 v1 … x15 y15 v15`, normalized), box auto-fit to visible keypoints + 2% margin.

## Development

- Backend: `cd backend; python -m venv .venv; .venv/bin/python -m pip install -r requirements.txt`; tests need Postgres (`docker run -d -e POSTGRES_USER=plt -e POSTGRES_PASSWORD=plt -e POSTGRES_DB=plt_test -p 6666:5432 postgres:16`) then `.venv/bin/python -m pytest`.
- Frontend: `cd frontend; npm install; npm test; npm run dev` (proxies `/api` to `http://localhost:8080`).
