# Pose Labeler Tool

A fast, single-purpose web app for reviewing and fixing model-generated 15-keypoint
YOLO-pose labels — multi-user, on a LAN. Replaces the `review_bad.py` / `dedup.py` /
`find_bad_labels.py` CLIs with a browser UI.

## Quick start

1. Install Docker (with the NVIDIA Container Toolkit if you want GPU inference).
2. Copy the config and point it at your dataset + models:
   ```
   cp .env.example .env
   # edit .env: DATASET_DIR, APP_PORT   (put your .pt models in <DATASET_DIR>/models/)
   ```
3. Check the port is free, then launch:
   ```
   python scripts/preflight.py
   docker compose up --build            # CPU
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build   # GPU
   ```
4. Open `http://localhost:8080` (or your `APP_PORT`), enter a username, pick a model
   and a task, and click Review.

The backend auto-scans the dataset into the database on first boot. To re-scan after
adding images, POST `/api/scan`.

## Config (`.env`)

| key | meaning |
|-----|---------|
| `DATASET_DIR` | host path to the dataset (`images/`, `labels/`, `models/`, the list files) — mounted read-write |
| `APP_PORT` | the single published host port (frontend) |

Models are listed from `<DATASET_DIR>/models/` (`.pt` files, recursive). Put your models there.

Postgres runs internally on the compose network and is never published. Data persists
in the `pgdata` volume.

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
- **Dedup** — review near-duplicate pairs side by side; delete (soft, to `.trash/`) or keep.

## Keyboard (review + editor)

- Review: `k` keep · `d` drop · `c` clear · `e` edit · `v`/←/→ view (GT / PRED / Clear) · `h` names · wheel zoom · drag pan · `0` reset.
- Editor: drag keypoint · drag inside box = move instance · right-click = cycle visibility · `n` click-to-place add (head→torso→legs→arms) · `s` skip bone · `x` delete · `ENTER` save · `ESC` cancel.

## Notes

- The backend runs a single uvicorn worker by design (serialized filesystem writes + a
  single GPU job worker). Do not scale it with `--workers`.
- Drops and dedup-deletes are soft (moved to `dataset/.trash/`), not unlinked.
- Stems are integer-sortable timestamp strings; the label format is YOLO-pose
  (`0 cx cy w h x1 y1 v1 … x15 y15 v15`, normalized), box auto-fit to visible keypoints + 2% margin.

## Development

- Backend: `cd backend; python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt`; tests need Postgres (`docker run -d -e POSTGRES_USER=plt -e POSTGRES_PASSWORD=plt -e POSTGRES_DB=plt_test -p 6666:5432 postgres:16`) then `.venv\Scripts\python -m pytest`.
- Frontend: `cd frontend; npm install; npm test; npm run dev` (proxies `/api` to `http://localhost:8080`).
