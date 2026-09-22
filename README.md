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
| `HF_TOKEN` | a HuggingFace token with read access to your dataset repos; optional, and datasets with a `repo:` show "no HF token configured" without it |

## Config (`config.yaml`)

These are backend settings, not `.env` vars — they live in `config.yaml` (see
`backend/config.example.yaml`), overridable the same way as any other field there:
`PLT_SYNC_ENABLED`, `PLT_SYNC_DEBOUNCE_SECONDS`, `PLT_SYNC_MAX_PENDING`.

| key | meaning |
|-----|---------|
| `sync_enabled` | default `true`; commit pending edits and deletions back to a dataset's repo automatically; `false` turns write-back off entirely |
| `sync_debounce_seconds` | default `60`; how long a batch of pending changes sits quiet before an automatic commit fires |
| `sync_max_pending` | default `50`; how many pending files force an immediate commit rather than waiting out the debounce |

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

## Downloading a dataset

A catalogued dataset with a `repo:` that is not yet on disk shows a Download button on
the setup screen. Downloading runs as a background job: it reports percentage, bytes and
a falling ETA, and survives a page reload — reopen the app and it re-attaches to the
same job in progress. The dataset becomes selectable once the download completes.

If a download is interrupted, the row still shows a Download button — the dataset reads
"download incomplete" rather than "not downloaded" or the ready size — and clicking it
again resumes from where the transfer stopped rather than restarting from scratch. A
dataset that is already fully downloaded refuses a second download (409) instead of
re-fetching in place.

## Syncing back

A dataset with a `repo:` writes back, too. Editing or dropping a label is a local
filesystem change first; the backend just remembers which files it owes the repo. Once
enough have piled up (`sync_max_pending`) or the oldest one has sat unsent for a while
(`sync_debounce_seconds`), it commits them automatically — no action needed. The setup
screen shows the count while it's waiting ("3 unsynced") with a **Sync now** button to
force the commit early instead of waiting out the debounce.

Only `images/` and `labels/` are ever committed. The per-installation review
bookkeeping — `reviewed_keep.txt`, `bad_labels.txt`, `model_labeled.txt` — stays local;
the real repo holds none of it, and pushing it would publish one reviewer's workflow.

If the remote branch has moved since the last sync, the dataset is marked diverged: the
row says so ("diverged — remote moved, sync paused") and offers no Sync button, because
a button that can't work is worse than an honest message. Divergence needs a human to
sort out; labelling keeps working locally, and pending changes are kept, not lost, for
whenever that's resolved. Set `sync_enabled: false` in `config.yaml` to turn off
write-back for every dataset.

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
