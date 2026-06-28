from app.inference import iou, suppress_overlaps, pred_to_instances


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((0, 0, 10, 10), (5, 0, 15, 10)) - (50 / 150)) < 1e-6


def test_suppress_overlaps_keeps_highest_conf():
    a = ((0, 0, 10, 10), 0.9, [])
    b = ((1, 1, 11, 11), 0.5, [])   # overlaps a
    c = ((100, 100, 110, 110), 0.7, [])  # disjoint
    kept = suppress_overlaps([b, a, c])
    confs = sorted(p[1] for p in kept)
    assert confs == [0.7, 0.9]      # b suppressed by a; c kept


def test_pred_to_instances_maps_visibility():
    kpts = [[10.0, 20.0, 0.9], [30.0, 40.0, 0.3], [50.0, 60.0, 0.05]] + [[0.0, 0.0, 0.0]] * 12
    out = pred_to_instances([((0, 0, 5, 5), 0.8, kpts)])
    assert len(out) == 1
    ks = out[0]["kpts"]
    assert len(ks) == 15
    assert ks[0] == [10.0, 20.0, 2]
    assert ks[1] == [30.0, 40.0, 1]
    assert ks[2] == [50.0, 60.0, 0]
