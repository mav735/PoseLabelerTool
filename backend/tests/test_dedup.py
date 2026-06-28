import numpy as np
from app.dedup import find_duplicates, diff


def test_diff():
    a = np.zeros((4, 4), np.float32)
    b = np.full((4, 4), 6.0, np.float32)
    assert diff(a, b) == 6.0


def test_find_duplicates_collapses_runs():
    base = np.zeros((4, 4), np.float32)
    near = np.full((4, 4), 1.0, np.float32)   # diff 1 < 3 -> dup of base
    far = np.full((4, 4), 50.0, np.float32)   # diff 50 -> new ref
    sigs = [base, near, near, far, near]       # idx0 ref; 1,2 dup of 0; 3 new ref; 4 (|1-50|=49) new ref
    dups = find_duplicates(sigs, thresh=3.0)
    assert dups == [(0, 1, 1.0), (0, 2, 1.0)]
