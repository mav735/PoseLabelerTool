def signature(path, hs=32):
    import cv2
    import numpy as np
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return cv2.resize(img, (hs, hs), interpolation=cv2.INTER_AREA).astype(np.float32)


def diff(sig_a, sig_b) -> float:
    import numpy as np
    return float(np.mean(np.abs(sig_a - sig_b)))


def find_duplicates(sigs, thresh=3.0):
    out = []
    if not sigs:
        return out
    ref = sigs[0]
    ref_idx = 0
    for i in range(1, len(sigs)):
        if diff(sigs[i], ref) < thresh:
            out.append((ref_idx, i, diff(sigs[i], ref)))
        else:
            ref, ref_idx = sigs[i], i
    return out
