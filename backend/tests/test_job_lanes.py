from types import SimpleNamespace

from app import jobs as jobs_mod
from app.hf.fake import FakeHFClient
from app.jobs import worker_once, TRANSFER_TYPES, COMPUTE_TYPES
from app.models import Job


def _cfg(tmp_path, catalog_text="datasets: []\nmodels: []\n"):
    root = tmp_path / "roots"
    root.mkdir(exist_ok=True)
    cat = root / "datasets.yaml"
    cat.write_text(catalog_text)
    return SimpleNamespace(datasets_root=root, models_root=root / "models",
                           catalog_path=cat)


REMOTE = "datasets:\n  - name: fresh\n    repo: a/b\n    revision: main\nmodels: []\n"


def test_the_compute_lane_ignores_a_download(db_session, tmp_path):
    db_session.add(Job(dataset="ds", type="download", params={}))
    db_session.commit()
    assert worker_once(lambda: db_session, _cfg(tmp_path), lane="compute") is None


def test_the_transfer_lane_ignores_an_oracle(db_session, tmp_path):
    db_session.add(Job(dataset="ds", type="oracle", params={"model": "m.pt"}))
    db_session.commit()
    assert worker_once(lambda: db_session, _cfg(tmp_path), lane="transfer") is None


def test_the_transfer_lane_picks_up_a_download(db_session, tmp_path, monkeypatch):
    # worker_once builds its own client, so the seam is patched here: no test
    # in this suite may reach the network.
    import app.hf.client as hf_client
    monkeypatch.setattr(hf_client, "make_client",
                        lambda: FakeHFClient(files={"images/000/1.jpg": b"xx"}))

    db_session.add(Job(dataset="fresh", type="download", params={}))
    db_session.commit()

    jid = worker_once(lambda: db_session, _cfg(tmp_path, REMOTE), lane="transfer")
    assert jid is not None
    row = db_session.get(Job, jid)          # re-fetch: worker_once closed the session
    assert row.status == "done", row.message


def test_the_compute_lane_picks_up_an_oracle(db_session, tmp_path):
    db_session.add(Job(dataset="ds", type="oracle", params={"model": "m.pt"}))
    db_session.commit()
    # The job then fails (no such dataset), but the lane CLAIMED it, which is
    # what this asserts — the lane filter, not the job body.
    assert worker_once(lambda: db_session, _cfg(tmp_path), lane="compute") is not None


def test_the_lanes_cover_every_job_type():
    # A type in neither lane would queue forever with no worker to run it.
    assert set(TRANSFER_TYPES) | set(COMPUTE_TYPES) == {
        "download", "model_download", "sync", "oracle", "dedup"}


def test_the_lanes_do_not_overlap():
    assert set(TRANSFER_TYPES) & set(COMPUTE_TYPES) == set()


def test_a_download_is_not_blocked_by_an_unready_dataset(db_session, tmp_path):
    # run_job refuses compute jobs whose dataset is not ready. A download runs
    # precisely BECAUSE it is not ready, so that guard must not apply to it.
    job = Job(dataset="fresh", type="download", params={})
    db_session.add(job); db_session.commit()
    jobs_mod.run_job(db_session, _cfg(tmp_path, REMOTE), job,
                     client=FakeHFClient(files={"images/000/1.jpg": b"xx"}))
    assert job.status == "done", job.message


def test_an_oracle_on_an_unready_dataset_still_fails_loudly(db_session, tmp_path):
    job = Job(dataset="gone", type="oracle", params={"model": "m.pt"})
    db_session.add(job); db_session.commit()
    jobs_mod.run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "error"
    assert "not ready" in job.message
