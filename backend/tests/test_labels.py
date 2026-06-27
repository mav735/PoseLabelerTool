from app.labels import (
    NUM_KPTS, KPT_NAMES, SKELETON, FLIP_IDX,
    Keypoint, Instance, parse_label, fit_box, format_instance, write_label_text,
)


def test_constants():
    assert NUM_KPTS == 15
    assert KPT_NAMES[0] == "hd" and KPT_NAMES[7] == "lw" and KPT_NAMES[14] == "rk"
    assert (3, 11) in SKELETON and (14, 10) in SKELETON and len(SKELETON) == 14
    assert FLIP_IDX == [0, 1, 2, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13]


def test_parse_empty_is_background():
    assert parse_label("") == []
    assert parse_label("\n\n") == []


def test_parse_full_line():
    line = "0 0.5 0.5 0.1 0.2 " + " ".join("0.40 0.30 2" for _ in range(15))
    insts = parse_label(line)
    assert len(insts) == 1
    i = insts[0]
    assert (i.cx, i.cy, i.w, i.h) == (0.5, 0.5, 0.1, 0.2)
    assert len(i.kpts) == 15
    assert i.kpts[0] == Keypoint(0.40, 0.30, 2)


def test_parse_short_line_skipped():
    assert parse_label("0 0.5 0.5") == []


def test_fit_box_none_when_no_points():
    assert fit_box([], [], 640, 640) is None


def test_fit_box_matches_reference_math():
    xs = [100.0, 200.0]
    ys = [50.0, 150.0]
    box = fit_box(xs, ys, 640, 640, margin=0.02)
    assert box == (98.0, 48.0, 202.0, 152.0)


def test_fit_box_clamps_to_bounds():
    box = fit_box([0.0, 640.0], [0.0, 640.0], 640, 640, margin=0.02)
    assert box == (0.0, 0.0, 640.0, 640.0)


def test_format_instance_matches_writer():
    kpts = [Keypoint(320.0, 320.0, 2)] + [Keypoint(0.0, 0.0, 0) for _ in range(14)]
    line = format_instance((300.0, 300.0, 340.0, 340.0), kpts, 640, 640)
    parts = line.split()
    assert parts[0] == "0"
    assert parts[1] == "0.500000" and parts[2] == "0.500000"
    assert parts[3] == "0.062500" and parts[4] == "0.062500"
    assert parts[5] == "0.500000" and parts[6] == "0.500000" and parts[7] == "2"
    assert parts[8] == "0.000000" and parts[10] == "0"


def test_write_label_text():
    assert write_label_text([]) == ""
    assert write_label_text(["a", "b"]) == "a\nb\n"
