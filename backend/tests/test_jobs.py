from pathlib import Path
from PIL import Image as PILImage
import app.inference as inference
from app.models import Image, Job, DedupPair
from app.jobs import run_job
from app.config import Config


def _ds(root: Path):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    for stem in ("100", "200", "300"):
        PILImage.new("RGB", (64, 64), (stem == "300" and (0, 0, 0) or (255, 255, 255))).save(root / "images" / f"{stem}.jpg")
        (root / "labels" / f"{stem}.txt").write_text("0 0.5 0.5 0.2 0.2 " + " ".join("0.5 0.5 2" for _ in range(15)))
    return root


def _cfg(root):
    return Config(dataset_dir=root, models_dir=root, db_url="x")


def test_oracle_job_writes_bad_labels(db_session, tmp_path, monkeypatch):
    _ds(tmp_path)
    db_session.add_all([Image(stem=s, has_label=True) for s in ("100", "200", "300")])
    db_session.commit()
    monkeypatch.setattr(inference, "load_model", lambda p: object())
    # model predicts nothing -> every labeled image is "missed GT" -> err 1.0 -> flagged
    monkeypatch.setattr(inference, "run_pred", lambda m, s, conf=0.15, iou_thr=0.45: [])
    job = Job(type="oracle", params={"model": "m.pt", "mode": "a", "threshold": 0.3})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "done"
    txt = (tmp_path / "bad_labels.txt").read_text()
    assert txt.count("\n") == 3   # all three flagged
    assert db_session.get(Image, "100").in_bad_labels is True


def test_dedup_job_builds_pairs(db_session, tmp_path):
    _ds(tmp_path)  # 100 & 300 white (near-identical), 200 black (different)
    job = Job(type="dedup", params={"pool": "all", "thresh": 3.0, "hash": 32})
    db_session.add(job); db_session.commit()
    run_job(db_session, _cfg(tmp_path), job)
    assert job.status == "done"
    pairs = db_session.query(DedupPair).all()
    # int order 100,200,300: 100 & 200 identical white -> 200 is a dup of 100; 300 black -> new ref.
    assert len(pairs) == 1
    assert pairs[0].keeper_stem == "100" and pairs[0].dup_stem == "200"
