import pytest
from types import SimpleNamespace
from app.hf.download import ProgressSink, run_download
from app.hf.fake import FakeHFClient
from app.hf.client import HFAuthError, HFError
from app.models import Job
from app.sync_state import read_sync, is_complete


def _cfg(root, catalog_path):
    return SimpleNamespace(datasets_root=root, models_root=root / "models",
                           catalog_path=catalog_path)


def _catalog(path, name="rust", repo="a/b"):
    path.write_text(f"datasets:\n  - name: {name}\n    repo: {repo}\n    revision: main\nmodels: []\n")
    return path


class _FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def advance(self, dt): self.t += dt


def test_sink_throttles_writes(db_session):
    job = Job(dataset="ds", type="download", params={})
    db_session.add(job); db_session.commit()
    clock = _FakeClock()
    sink = ProgressSink(db_session, job, 1000, now=clock, min_interval=0.5)
    sink.add(100)                      # first add always lands
    assert job.processed == 100
    sink.add(100)                      # too soon: buffered, not written
    assert job.processed == 100
    clock.advance(1.0)
    sink.add(100)
    assert job.processed == 300        # buffered bytes included


def test_sink_records_total_rate_and_eta(db_session):
    job = Job(dataset="ds", type="download", params={})
    db_session.add(job); db_session.commit()
    clock = _FakeClock()
    sink = ProgressSink(db_session, job, 1000, now=clock, min_interval=0.0)
    sink.add(200)
    clock.advance(2.0)
    sink.add(200)
    assert job.total == 1000
    assert job.processed == 400
    assert job.meta["rate_bps"] > 0
    assert job.meta["eta_seconds"] is not None


def test_sink_records_file_counts(db_session):
    job = Job(dataset="ds", type="download", params={})
    db_session.add(job); db_session.commit()
    sink = ProgressSink(db_session, job, 1000, now=_FakeClock(), min_interval=0.0)
    sink.add_files(1, 4)
    sink.add_files(1, 4)
    assert job.meta["files_done"] == 2
    assert job.meta["files_total"] == 4


def test_sink_survives_concurrent_reporters(db_session):
    """snapshot_download reports from ~8 threads; none of them may be lost.

    Probabilistic, not a proof. At the DEFAULT GIL switch interval this test
    passes against knowingly-unlocked code — it has almost no signal. Tightening
    the switch interval for its duration is what makes the race actually land;
    without that, this test is decoration. Restore the interval afterwards so
    the setting does not leak into the rest of the suite.
    """
    import sys
    import threading

    job = Job(dataset="ds", type="download", params={})
    db_session.add(job); db_session.commit()
    # Default min_interval: the buffered path is the one under contention, and
    # this avoids 800 serialized Postgres commits.
    sink = ProgressSink(db_session, job, 8000)

    def worker():
        for _ in range(100):
            sink.add(10)

    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(previous)

    sink.flush()
    assert job.processed == 8000


def test_human_bytes_reads_as_sizes():
    from app.hf.download import human_bytes
    assert human_bytes(512) == "512 B"
    assert human_bytes(2 * 1024 * 1024) == "2.0 MB"
    assert human_bytes(3 * 1024 ** 3) == "3.0 GB"


def test_running_out_of_space_names_both_numbers(db_session, tmp_path):
    from app.hf.client import HFDiskFull
    cat = _catalog(tmp_path / "datasets.yaml")
    job = Job(dataset="rust", type="download", params={})
    db_session.add(job); db_session.commit()
    client = FakeHFClient(size=1024 ** 3, raises=None)
    client.snapshot = lambda *a, **k: (_ for _ in ()).throw(HFDiskFull("out of space"))
    with pytest.raises(HFDiskFull) as ei:
        run_download(db_session, _cfg(tmp_path, cat), job, {}, client)
    assert "ran out of space at" in str(ei.value)
    assert "1.0 GB" in str(ei.value)


def test_sink_eta_is_none_before_any_rate(db_session):
    job = Job(dataset="ds", type="download", params={})
    db_session.add(job); db_session.commit()
    sink = ProgressSink(db_session, job, 1000, now=_FakeClock(), min_interval=0.0)
    sink.add(10)
    assert job.meta["eta_seconds"] is None


def test_download_writes_files_and_marks_complete(db_session, tmp_path):
    cat = _catalog(tmp_path / "datasets.yaml")
    job = Job(dataset="rust", type="download", params={})
    db_session.add(job); db_session.commit()
    client = FakeHFClient(files={"images/000/1.jpg": b"xxxx", "labels/000/1.txt": b"y"},
                          sha="abc123")
    run_download(db_session, _cfg(tmp_path, cat), job, {}, client)
    ds = tmp_path / "rust"
    assert (ds / "images" / "000" / "1.jpg").exists()
    assert read_sync(ds)["revision"] == "abc123"
    assert is_complete(ds) is True
    assert job.processed == job.total == 5


def test_download_uses_local_dir_not_the_shared_cache(db_session, tmp_path):
    cat = _catalog(tmp_path / "datasets.yaml")
    job = Job(dataset="rust", type="download", params={})
    db_session.add(job); db_session.commit()
    client = FakeHFClient(files={"a.txt": b"a"})
    run_download(db_session, _cfg(tmp_path, cat), job, {}, client)
    repo_id, revision, local_dir, repo_type = client.snapshot_calls[0]
    assert local_dir == str(tmp_path / "rust")
    assert repo_type == "dataset"


def test_a_failed_download_leaves_the_dataset_not_ready(db_session, tmp_path):
    cat = _catalog(tmp_path / "datasets.yaml")
    job = Job(dataset="rust", type="download", params={})
    db_session.add(job); db_session.commit()
    client = FakeHFClient(files={"images/000/1.jpg": b"xx", "images/000/2.jpg": b"yy"},
                          fail_after_bytes=2)
    with pytest.raises(HFError):
        run_download(db_session, _cfg(tmp_path, cat), job, {}, client)
    ds = tmp_path / "rust"
    assert is_complete(ds) is False     # marker says incomplete, so not selectable
    assert job.processed == 2           # bytes transferred are recorded


def test_download_refuses_a_catalog_entry_with_no_repo(db_session, tmp_path):
    cat = tmp_path / "datasets.yaml"
    cat.write_text("datasets:\n  - name: localonly\nmodels: []\n")
    job = Job(dataset="localonly", type="download", params={})
    db_session.add(job); db_session.commit()
    with pytest.raises(ValueError):
        run_download(db_session, _cfg(tmp_path, cat), job, {}, FakeHFClient())


def test_auth_failure_message_never_contains_the_token(db_session, tmp_path):
    cat = _catalog(tmp_path / "datasets.yaml")
    job = Job(dataset="rust", type="download", params={})
    db_session.add(job); db_session.commit()
    client = FakeHFClient(raises=HFAuthError("not authorised for a/b"))
    with pytest.raises(HFAuthError) as ei:
        run_download(db_session, _cfg(tmp_path, cat), job, {}, client)
    assert "hf_" not in str(ei.value)
