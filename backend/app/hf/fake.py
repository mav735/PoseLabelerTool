"""An in-memory stand-in for HFClient, so nothing else needs the network."""
from pathlib import Path
from typing import Callable

from app.hf.client import HFError, HFNotFound


class FakeHFClient:
    def __init__(self, files: dict[str, bytes] | None = None, size: int | None = None,
                 sha: str = "fakesha", raises: Exception | None = None,
                 fail_after_bytes: int | None = None, has_token: bool = True):
        self.files = files or {}
        self._size = size if size is not None else sum(len(v) for v in self.files.values())
        self._sha = sha
        self._raises = raises
        self._fail_after = fail_after_bytes
        self.has_token = has_token
        self.snapshot_calls: list[tuple] = []

    def _maybe_raise(self):
        if self._raises is not None:
            raise self._raises

    def repo_size(self, repo_id, revision="main", repo_type="dataset") -> int:
        self._maybe_raise()
        return self._size

    def file_size(self, repo_id, filename, repo_type="model", revision="main") -> int:
        self._maybe_raise()
        if filename not in self.files:
            raise HFNotFound(f"no such file in repository: {filename}")
        return len(self.files[filename])

    def repo_sha(self, repo_id, revision="main", repo_type="dataset") -> str:
        self._maybe_raise()
        return self._sha

    def snapshot(self, repo_id, revision, local_dir, repo_type="dataset",
                 on_bytes: Callable[[int], None] | None = None,
                 on_files: Callable[[int, int], None] | None = None) -> str:
        self._maybe_raise()
        self.snapshot_calls.append((repo_id, revision, str(local_dir), repo_type))
        written = 0
        for name, blob in self.files.items():
            if self._fail_after is not None and written >= self._fail_after:
                raise HFError("fake transfer interrupted")
            p = Path(local_dir) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)
            written += len(blob)
            if on_bytes:
                on_bytes(len(blob))
            if on_files:
                on_files(1, len(self.files))
        return str(local_dir)

    def fetch_file(self, repo_id, filename, local_dir,
                   on_bytes: Callable[[int], None] | None = None) -> str:
        self._maybe_raise()
        if filename not in self.files:
            raise HFNotFound(f"no such file in repository: {filename}")
        blob = self.files[filename]
        p = Path(local_dir) / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
        if on_bytes and blob:
            on_bytes(len(blob))
        return str(p)
