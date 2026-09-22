"""The only module that talks to HuggingFace.

Everything else takes a client object, so the rest of the system tests
offline against `fake.FakeHFClient`. Keeping the network behind one seam
is what makes that possible — do not import `huggingface_hub` elsewhere.
"""
import errno
import os
import threading
from typing import Callable

TOKEN_ENV = "PLT_HF_TOKEN"


class _NullWriter:
    """Swallows tqdm's rendering. Progress is reported through the job row."""
    def write(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass


_NULL_WRITER = _NullWriter()


class HFError(Exception):
    """Any failure talking to HuggingFace."""


class HFAuthError(HFError):
    """Not authorised for this repo — missing, invalid or unprivileged token."""


class HFNotFound(HFError):
    """The repo or revision does not exist."""


class HFDiskFull(HFError):
    """The filesystem ran out of space mid-transfer."""


class HFConflict(HFError):
    """The remote branch moved; our parent_commit no longer matches."""


def token_from_env() -> str | None:
    tok = os.environ.get(TOKEN_ENV)
    return tok or None


def _progress_class(on_bytes: Callable[[int], None] | None = None,
                    on_files: Callable[[int, int], None] | None = None):
    """A tqdm subclass that splits byte progress from file progress.

    `snapshot_download` builds two `unit="B"` bars from this class: one counting
    network bytes (deduplicated, so smaller than the files) and one counting
    bytes written to disk. Both call `update()`. They measure the same transfer,
    so the honest figure is the furthest-along bar — summing them double-counts,
    reporting close to twice the real size. Tracking each bar and emitting the
    delta of the maximum stays correct whether the library makes one bar or five.
    """
    from tqdm.auto import tqdm as _tqdm

    if on_bytes is None and on_files is None:
        return _tqdm

    seen: dict[int, int] = {}
    keep: list = []          # hold references so ids cannot be recycled
    emitted = 0
    lock = threading.Lock()

    class _ReportingTqdm(_tqdm):
        def __init__(self, *args, **kwargs):
            # Force the sink unconditionally, not via setdefault:
            # huggingface_hub passes its own `file` in some paths, and a bar
            # that renders "sometimes" is the worst outcome.
            kwargs["file"] = _NULL_WRITER
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            nonlocal emitted
            if n:
                if getattr(self, "unit", None) == "B":
                    if on_bytes is not None:
                        # `snapshot_download` runs up to `max_workers` (8 by
                        # default) file downloads concurrently, and each one
                        # calls update() on these same bar instances from its
                        # own thread — so the accounting below needs a lock.
                        # The callback itself runs OUTSIDE the lock: it may
                        # commit to Postgres downstream, and holding the lock
                        # across that would serialize 8 threads behind the
                        # slowest write. Deltas are order-independent, so
                        # releasing before calling out is safe.
                        delta = 0
                        with lock:
                            key = id(self)
                            if key not in seen:
                                keep.append(self)
                            seen[key] = seen.get(key, 0) + int(n)
                            best = max(seen.values())
                            if best > emitted:
                                delta = best - emitted
                                emitted = best
                        if delta:
                            on_bytes(delta)
                elif on_files is not None:
                    on_files(int(n), int(getattr(self, "total", 0) or 0))
            return super().update(n)

    return _ReportingTqdm


def _translate(exc: Exception) -> HFError:
    from huggingface_hub.utils import (EntryNotFoundError, GatedRepoError,
                                       HfHubHTTPError, RepositoryNotFoundError)
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        # Caught before the generic handler: run_download re-raises this with
        # the byte counts, which only it knows.
        return HFDiskFull("out of space")
    if isinstance(exc, (GatedRepoError,)):
        return HFAuthError("not authorised for this repository")
    if isinstance(exc, (RepositoryNotFoundError, EntryNotFoundError)):
        return HFNotFound("repository or file not found")
    if isinstance(exc, HfHubHTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return HFAuthError("not authorised for this repository")
        if status == 404:
            return HFNotFound("repository or file not found")
        if status == 412:
            return HFConflict("remote branch has moved since the last sync")
        return HFError(f"HuggingFace returned HTTP {status}")
    return HFError(str(exc)[:200])


class HFClient:
    def __init__(self, token: str | None = None):
        self._token = token

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    def _api(self):
        from huggingface_hub import HfApi
        return HfApi(token=self._token)

    def repo_size(self, repo_id: str, revision: str = "main",
                  repo_type: str = "dataset") -> int:
        try:
            info = self._api().repo_info(repo_id, repo_type=repo_type,
                                         revision=revision, files_metadata=True)
        except Exception as e:                      # noqa: BLE001 - translated below
            raise _translate(e) from None
        total = 0
        for s in (info.siblings or []):
            total += int(getattr(s, "size", 0) or 0)
        return total

    def file_size(self, repo_id: str, filename: str, repo_type: str = "model",
                  revision: str = "main") -> int:
        """The size of ONE file. A model repo may hold several checkpoints."""
        try:
            info = self._api().repo_info(repo_id, repo_type=repo_type,
                                         revision=revision, files_metadata=True)
        except Exception as e:                      # noqa: BLE001
            raise _translate(e) from None
        for s in (info.siblings or []):
            if getattr(s, "rfilename", None) == filename:
                return int(getattr(s, "size", 0) or 0)
        raise HFNotFound(f"no such file in repository: {filename}")

    def repo_sha(self, repo_id: str, revision: str = "main",
                 repo_type: str = "dataset") -> str:
        try:
            info = self._api().repo_info(repo_id, repo_type=repo_type,
                                         revision=revision)
        except Exception as e:                      # noqa: BLE001
            raise _translate(e) from None
        return str(info.sha or "")

    def snapshot(self, repo_id: str, revision: str, local_dir,
                 repo_type: str = "dataset",
                 on_bytes: Callable[[int], None] | None = None,
                 on_files: Callable[[int, int], None] | None = None) -> str:
        from huggingface_hub import snapshot_download
        try:
            return snapshot_download(
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision,
                # local_dir is REQUIRED: the default cache symlinks into a
                # shared store, and this app edits label files in place.
                local_dir=str(local_dir),
                token=self._token,
                tqdm_class=_progress_class(on_bytes, on_files),
            )
        except Exception as e:                      # noqa: BLE001
            raise _translate(e) from None

    def fetch_file(self, repo_id: str, filename: str, local_dir,
                   on_bytes: Callable[[int], None] | None = None) -> str:
        from huggingface_hub import hf_hub_download
        try:
            return hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                repo_type="model",
                local_dir=str(local_dir),
                token=self._token,
                tqdm_class=_progress_class(on_bytes),
            )
        except Exception as e:                      # noqa: BLE001
            raise _translate(e) from None

    def commit(self, repo_id: str, revision: str, adds, deletes, message: str,
               parent_commit: str | None = None, repo_type: str = "dataset") -> str:
        """Commit adds and deletes as one atomic change.

        `adds` is (repo_path, local_path) pairs; `deletes` is repo paths. The
        CommitOperation objects are built here and never escape this module —
        that containment is what keeps every other module testable offline.
        """
        from huggingface_hub import CommitOperationAdd, CommitOperationDelete
        ops = [CommitOperationAdd(path_in_repo=rp, path_or_fileobj=lp)
               for rp, lp in adds]
        ops += [CommitOperationDelete(path_in_repo=p) for p in deletes]
        try:
            info = self._api().create_commit(
                repo_id=repo_id, repo_type=repo_type, revision=revision,
                operations=ops, commit_message=message,
                parent_commit=parent_commit,
            )
        except Exception as e:                      # noqa: BLE001
            raise _translate(e) from None
        return str(getattr(info, "oid", "") or "")


def make_client() -> HFClient:
    return HFClient(token_from_env())
