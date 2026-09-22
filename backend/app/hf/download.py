"""The body of a download job: fetch a repo into its dataset directory."""
import threading
import time
from collections import deque
from pathlib import Path

from app.catalog import load_catalog
from app.datasets_mgr import safe_dataset_path
from app.hf.client import HFDiskFull
from app.sync_state import SYNC_FILE, write_sync

# How much history the rolling rate keeps. A cumulative average on a link
# that swings between 0.4 and 1 MB/s gives an ETA that is confidently wrong
# for most of a long download; a short window tracks what is happening now.
_RATE_WINDOW_SECONDS = 10.0


def human_bytes(n: int) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class ProgressSink:
    """Accumulates byte deltas and writes them to the job, throttled.

    A 2.62 GB snapshot delivers progress in thousands of small callbacks.
    Committing each one would hammer Postgres for no benefit, so bytes are
    buffered and flushed at most every `min_interval` seconds.
    """

    def __init__(self, session, job, total_bytes: int, *,
                 now=time.monotonic, min_interval: float = 0.5, initial: int = 0):
        self._session = session
        self._job = job
        self._now = now
        self._min_interval = min_interval
        self._pending = 0
        self._done = int(initial)
        self._files_done = 0
        self._files_total = 0
        self._last_write = None
        self._samples: deque = deque()
        # snapshot_download fans out over 8 threads by default and they all
        # report into this sink. Beyond losing counts, the commit in _write
        # would be a SQLAlchemy Session used from several threads at once.
        self._lock = threading.Lock()
        job.total = int(total_bytes)
        job.processed = min(self._done, job.total)
        job.meta = {"rate_bps": 0.0, "eta_seconds": None,
                    "files_done": 0, "files_total": 0}
        session.commit()

    def add(self, n: int) -> None:
        with self._lock:
            self._pending += int(n)
            t = self._now()
            if self._last_write is not None and (t - self._last_write) < self._min_interval:
                return
            self._write(t)

    def add_files(self, n: int, total: int) -> None:
        with self._lock:
            self._files_done += int(n)
            self._files_total = max(self._files_total, int(total))
            t = self._now()
            if self._last_write is not None and (t - self._last_write) < self._min_interval:
                return
            self._write(t)

    def flush(self) -> None:
        with self._lock:
            self._write(self._now())

    def _write(self, t: float) -> None:
        self._done += self._pending
        self._pending = 0
        self._samples.append((t, self._done))
        while len(self._samples) > 1 and (t - self._samples[0][0]) > _RATE_WINDOW_SECONDS:
            self._samples.popleft()

        rate = 0.0
        if len(self._samples) > 1:
            t0, b0 = self._samples[0]
            dt = t - t0
            if dt > 0:
                rate = (self._done - b0) / dt

        remaining = max(0, int(self._job.total) - self._done)
        eta = (remaining / rate) if rate > 0 else None

        # `_done` itself stays unclamped -- rate/ETA are computed from deltas
        # between samples, and clamping it here would flatten those deltas
        # once a bloated `initial` estimate has already hit the total. Only
        # the reported figure is capped, so a directory holding extra files
        # can never show more than 100%.
        self._job.processed = min(self._done, int(self._job.total))
        self._job.meta = {"rate_bps": round(rate, 1),
                          "eta_seconds": round(eta) if eta is not None else None,
                          "files_done": self._files_done,
                          "files_total": self._files_total}
        self._last_write = t
        self._session.commit()


def _payload_bytes(ds_dir) -> int:
    """Bytes of repo content already on disk.

    Comparable with `repo_size`: excludes HF's `.cache/` (incomplete blobs and
    metadata, not payload) and our own sync marker.
    """
    root = Path(ds_dir)
    total = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] == ".cache":
            continue
        if rel.name == SYNC_FILE:
            continue
        total += p.stat().st_size
    return total


def run_download(session, cfg, job, client) -> None:
    """Fetch `job.dataset`'s repo into its directory under datasets_root."""
    cat = load_catalog(cfg.catalog_path)
    entry = next((d for d in cat.datasets if d.name == job.dataset), None)
    if entry is None:
        raise ValueError(f"dataset not in catalog: {job.dataset!r}")
    if not entry.repo:
        raise ValueError(f"dataset is local-only, nothing to download: {job.dataset!r}")

    ds_dir = safe_dataset_path(cfg.datasets_root, job.dataset)

    # Resolve the repo BEFORE creating anything. A repo that cannot be reached
    # must leave no directory behind, or `discover()` reports a dataset that was
    # never downloaded as local and the row reads "missing images/".
    sha = client.repo_sha(entry.repo, entry.revision)
    total = client.repo_size(entry.repo, entry.revision)

    ds_dir.mkdir(parents=True, exist_ok=True)
    # Mark incomplete BEFORE fetching, so an interrupted download leaves a
    # dataset that readiness refuses rather than one that looks usable.
    write_sync(ds_dir, revision=sha, completed=False)

    # Files already complete are skipped by snapshot_download and never reported
    # through on_bytes, so without this a resumed download shows a bar that
    # starts from zero and finishes well short of 100%.
    already = min(_payload_bytes(ds_dir), total)
    sink = ProgressSink(session, job, total, initial=already)
    try:
        client.snapshot(entry.repo, entry.revision, ds_dir,
                        on_bytes=sink.add, on_files=sink.add_files)
    except HFDiskFull:
        # The client knows the errno; only we know how far we got.
        #
        # This flush is ORDERING-CRITICAL, not redundant with the `finally`.
        # The f-string below reads job.processed, and it is evaluated BEFORE
        # the finally runs — so without this, the message reports only what the
        # last throttled write persisted and silently drops whatever is still
        # buffered in the sink. Naming how far it got is the entire purpose of
        # this message. Do not remove it as a duplicate.
        sink.flush()
        raise HFDiskFull(f"ran out of space at {human_bytes(job.processed)} "
                         f"of {human_bytes(job.total)}") from None
    finally:
        sink.flush()

    write_sync(ds_dir, revision=sha, completed=True)
    job.result = {"revision": sha, "bytes": job.processed}
    session.commit()
