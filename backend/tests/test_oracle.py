from app.oracle import bbox_iou, kpt_distance, score_image_a, score_image_b


def test_bbox_iou():
    assert bbox_iou((50, 50, 100, 100), (50, 50, 100, 100)) == 1.0 - 1e-12 or abs(bbox_iou((50, 50, 100, 100), (50, 50, 100, 100)) - 1.0) < 1e-3
    assert bbox_iou((0, 0, 10, 10), (100, 100, 10, 10)) < 1e-6


def _kpts(dx=0.0, v=2):
    return [(100 + dx, 100, v)] * 15


def test_kpt_distance_zero_when_aligned():
    gt = _kpts(0)
    pred = [(100.0, 100.0, 0.9)] * 15
    assert kpt_distance(gt, pred, 2500.0) == 0.0


def test_score_a_perfect_match_low_err():
    gt = [{"bbox": (100, 100, 50, 50), "kpts": _kpts(0)}]
    preds = [{"bbox": (100, 100, 50, 50), "conf": 0.9, "kpts": [(100.0, 100.0, 0.9)] * 15}]
    err, _ = score_image_a(gt, preds)
    assert err < 0.05


def test_score_a_missed_gt_is_one():
    gt = [{"bbox": (100, 100, 50, 50), "kpts": _kpts(0)}]
    err, reason = score_image_a(gt, [])
    assert err == 1.0 and "missed" in reason


def test_score_a_fp_on_background():
    err, reason = score_image_a([], [{"bbox": (10, 10, 50, 50), "conf": 0.8, "kpts": [(10.0, 10.0, 0.9)] * 15}])
    assert err >= 0.5 and "FP" in reason


def test_score_b_flags_big_confident_offset():
    # 50px box (side>=40), conf 0.9, keypoints offset 30px -> max dist/sqrt(2500)=30/50=0.6
    gt = [{"bbox": (100, 100, 50, 50), "kpts": [(100.0, 100.0, 2)] * 15}]
    preds = [{"bbox": (100, 100, 50, 50), "conf": 0.9, "kpts": [(130.0, 100.0, 0.9)] * 15}]
    score, _ = score_image_b(gt, preds)
    assert abs(score - 0.6) < 1e-6


def test_score_b_ignores_small_or_lowconf():
    gt = [{"bbox": (100, 100, 20, 20), "kpts": [(100.0, 100.0, 2)] * 15}]  # side 20 < 40
    preds = [{"bbox": (100, 100, 20, 20), "conf": 0.9, "kpts": [(130.0, 100.0, 0.9)] * 15}]
    score, _ = score_image_b(gt, preds)
    assert score == 0.0
