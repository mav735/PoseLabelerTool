from pathlib import Path
from types import SimpleNamespace
from PIL import Image as PILImage
import app.inference as inference
from app.models import Image, Job, DedupPair
from app.jobs import run_job
from app.config import Config


def _write_jpg(path: Path, color=(255, 255, 255)):
    PILImage.new("RGB", (64, 64), color).save(path)


def _ds(datasets_root: Path, name: str = "ds"):
    d = datasets_root / name
    (d / "images").mkdir(parents=True)
    (d / "labels").mkdir(parents=True)
    for stem in ("100", "200", "300"):
        _write_jpg(d / "images" / f"{stem}.jpg", (0, 0, 0) if stem == "300" else (255, 255, 255))
        (d / "labels" / f"{stem}.txt").write_text("0 0.5 0.5 0.2 0.2 " + " ".join("0.5 0.5 2" for _ in range(15)))
    return d


def _cfg(root):
    return Config(datasets_root=root, models_root=root, db_url="x")


def test_oracle_job_writes_bad_labels(db_session, tmp_path, monkeypatch):
    _ds(tmp_path, "ds")
    db_session.add_all([Image(dataset="ds", stem=s, has_label=True) for s in ("100", "200", "300")])
    db_session.commit()
    monkeypatch.setattr(inference, "load_model", lambda p: object())
    # model predicts nothing -> every labeled image is "missed GT" -> err 1.0 -> flagged
    monkeypatch.setattr(inference, "run_pred", lambda m, s, conf=0.15, iou_thr=0.45: [])
    job = Job(dataset="ds", type="oracle", params={"model": "m.pt", "mode": "a", "threshold": 0.3})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "done"
    txt = (tmp_path / "ds" / "bad_labels.txt").read_text()
    assert txt.count("\n") == 3   # all three flagged
    assert db_session.get(Image, ("ds", "100")).in_bad_labels is True


def test_oracle_job_fails_loudly_when_dataset_dir_is_gone(db_session, tmp_path):
    # No images/ subdirectory -- e.g. the dataset directory vanished between
    # the job being queued and run. Without a readiness guard, image_stems
    # would glob nothing and the oracle would happily write an empty
    # bad_labels.txt, silently clearing every existing flag.
    db_session.add(Image(dataset="ds", stem="100", has_label=True, in_bad_labels=True))
    job = Job(dataset="ds", type="oracle", params={"model": "m.pt", "mode": "a", "threshold": 0.3})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "error"
    assert job.message
    assert not (tmp_path / "ds" / "bad_labels.txt").exists()
    assert db_session.get(Image, ("ds", "100")).in_bad_labels is True  # untouched, not cleared


def test_dedup_job_fails_loudly_when_dataset_dir_is_gone(db_session, tmp_path):
    job = Job(dataset="ds", type="dedup", params={"pool": "all", "thresh": 3.0, "hash": 32})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "error"
    assert job.message


def test_dedup_job_builds_pairs(db_session, tmp_path):
    _ds(tmp_path, "ds")  # 100 & 200 white (near-identical), 300 black (different)
    job = Job(dataset="ds", type="dedup", params={"pool": "all", "thresh": 3.0, "hash": 32})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "done"
    pairs = db_session.query(DedupPair).all()
    # int order 100,200,300: 100 & 200 identical white -> 200 is a dup of 100; 300 black -> new ref.
    assert len(pairs) == 1
    assert pairs[0].keeper_stem == "100" and pairs[0].dup_stem == "200"


def test_dedup_rerun_does_not_accumulate(db_session, tmp_path):
    _ds(tmp_path, "ds")  # 100 & 200 identical white, 300 black -> exactly 1 pair
    p = {"pool": "all", "thresh": 3.0, "hash": 32}
    j1 = Job(dataset="ds", type="dedup", params=p); db_session.add(j1); db_session.commit()
    run_job(db_session, _cfg(tmp_path), j1)
    j2 = Job(dataset="ds", type="dedup", params=p); db_session.add(j2); db_session.commit()
    run_job(db_session, _cfg(tmp_path), j2)
    assert db_session.query(DedupPair).filter_by(status="todo").count() == 1  # not 2
    assert j2.result["pairs"] == 1


def test_dedup_pairs_carry_the_job_dataset(db_session, tmp_path, monkeypatch):
    root = tmp_path / "roots"
    d = root / "ds-a"
    (d / "images").mkdir(parents=True)
    for stem in ("100", "101"):
        _write_jpg(d / "images" / f"{stem}.jpg")
    cfg = SimpleNamespace(datasets_root=root, models_root=tmp_path / "m",
                          dedup_thresh=3.0, dedup_hash=32)
    job = Job(dataset="ds-a", type="dedup", params={"pool": "all"}, status="queued")
    db_session.add(job)
    db_session.commit()
    run_job(db_session, cfg, job)
    assert job.status == "done"
    for pair in db_session.query(DedupPair).all():
        assert pair.dataset == "ds-a"


def test_oracle_does_not_touch_other_datasets_flags(db_session, tmp_path, monkeypatch):
    _ds(tmp_path, "ds-a")
    db_session.add_all([Image(dataset="ds-a", stem=s, has_label=True) for s in ("100", "200", "300")])
    # ds-b's stem ("999") is never in ds-a's run, so an unfiltered loop would still
    # clear it to False; the dataset filter must leave it alone entirely.
    db_session.add(Image(dataset="ds-b", stem="999", in_bad_labels=True))
    db_session.commit()
    monkeypatch.setattr(inference, "load_model", lambda p: object())
    # model predicts nothing -> every labeled image is "missed GT" -> err 1.0 -> flagged
    monkeypatch.setattr(inference, "run_pred", lambda m, s, conf=0.15, iou_thr=0.45: [])
    job = Job(dataset="ds-a", type="oracle", params={"model": "m.pt", "mode": "a", "threshold": 0.3})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "done"
    assert db_session.get(Image, ("ds-b", "999")).in_bad_labels is True


def test_dedup_leaves_other_datasets_pending_pairs(db_session, tmp_path):
    _ds(tmp_path, "ds-a")  # 100 & 200 white (near-identical) -> produces a todo pair, pool "all"
    other = DedupPair(dataset="ds-b", keeper_stem="1", dup_stem="2", diff=0.0, pool="all", status="todo")
    db_session.add(other)
    db_session.commit()
    other_id = other.id
    job = Job(dataset="ds-a", type="dedup", params={"pool": "all", "thresh": 3.0, "hash": 32})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "done"
    row = db_session.get(DedupPair, other_id)
    assert row is not None
    assert row.status == "todo"
