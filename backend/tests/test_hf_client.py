import io
import sys
import threading

import pytest
from app.hf.client import _progress_class, token_from_env, HFError, HFAuthError, HFNotFound
from app.hf.fake import FakeHFClient


def test_token_from_env_reads_plt_hf_token(monkeypatch):
    monkeypatch.setenv("PLT_HF_TOKEN", "hf_example")
    assert token_from_env() == "hf_example"


def test_token_from_env_is_none_when_unset(monkeypatch):
    monkeypatch.delenv("PLT_HF_TOKEN", raising=False)
    assert token_from_env() is None


def test_fake_reports_size_and_sha():
    c = FakeHFClient(size=1234, sha="deadbeef")
    assert c.repo_size("a/b") == 1234
    assert c.repo_sha("a/b") == "deadbeef"


def test_fake_snapshot_writes_files_and_reports_bytes(tmp_path):
    c = FakeHFClient(files={"images/000/1.jpg": b"xxxx", "labels/000/1.txt": b"y"})
    seen = []
    c.snapshot("a/b", "main", tmp_path, on_bytes=seen.append)
    assert (tmp_path / "images" / "000" / "1.jpg").read_bytes() == b"xxxx"
    assert (tmp_path / "labels" / "000" / "1.txt").read_bytes() == b"y"
    assert sum(seen) == 5


def test_fake_snapshot_reports_file_counts(tmp_path):
    c = FakeHFClient(files={"a.txt": b"x", "b.txt": b"y", "c.txt": b"z"})
    files = []
    c.snapshot("a/b", "main", tmp_path, on_files=lambda n, total: files.append((n, total)))
    assert sum(n for n, _ in files) == 3
    assert files[0][1] == 3


def test_fake_file_size_is_the_one_file_not_the_repo():
    c = FakeHFClient(files={"small.pt": b"xx", "huge.pt": b"x" * 100})
    assert c.repo_size("a/m") == 102
    assert c.file_size("a/m", "small.pt") == 2


def test_fake_can_raise_auth():
    c = FakeHFClient(raises=HFAuthError("not authorised for a/b"))
    with pytest.raises(HFAuthError):
        c.repo_size("a/b")


def test_fake_can_fail_partway_through(tmp_path):
    c = FakeHFClient(files={"a.txt": b"aa", "b.txt": b"bb"}, fail_after_bytes=2)
    seen = []
    with pytest.raises(HFError):
        c.snapshot("a/b", "main", tmp_path, on_bytes=seen.append)
    assert sum(seen) == 2          # progress reported up to the failure


def test_fake_fetch_file_raises_not_found_for_an_unknown_filename(tmp_path):
    # HFClient.fetch_file raises HFNotFound for a missing file; the fake must
    # match that or a future model-download test would pass green against
    # behaviour production does not have.
    c = FakeHFClient(files={"known.pt": b"xx"})
    with pytest.raises(HFNotFound):
        c.fetch_file("a/m", "missing.pt", tmp_path)


def test_fake_has_token_reflects_construction():
    assert FakeHFClient(has_token=False).has_token is False
    assert FakeHFClient().has_token is True


def test_progress_class_reports_furthest_bar_not_the_sum_of_both():
    # huggingface_hub 1.x builds TWO unit="B" bars for one snapshot download
    # (network bytes, then bytes reconstructed to disk). Both call update().
    # They measure the same transfer, so summing their deltas double-counts
    # it; the honest total is whichever bar is furthest along.
    #
    # tqdm's __init__ short-circuits when disable=True and never sets `unit`
    # at all (verified: hasattr(bar, "unit") is False), so bars here are
    # built with file=io.StringIO() instead, which does set `unit` normally.
    byte_events = []
    file_events = []
    cls = _progress_class(on_bytes=byte_events.append,
                          on_files=lambda n, total: file_events.append((n, total)))

    network_bar = cls(total=16, unit="B", file=io.StringIO())
    disk_bar = cls(total=16, unit="B", file=io.StringIO())

    network_bar.update(5)   # network: 5   -> forwarded max delta: 5
    disk_bar.update(6)      # disk:    6   -> forwarded max delta: 1  (6-5)
    network_bar.update(3)   # network: 8   -> forwarded max delta: 2  (8-6)
    disk_bar.update(10)     # disk:    16  -> forwarded max delta: 8  (16-8)

    assert sum(byte_events) == 16          # max(8, 16), not the sum (24)

    files_bar = cls(total=3)  # no unit="B" -> routed to on_files, not on_bytes
    files_bar.update(1)
    assert file_events == [(1, 3)]
    assert sum(byte_events) == 16          # unchanged by the file-count bar


def test_progress_class_stays_correct_under_concurrent_updates():
    # `snapshot_download` runs up to `max_workers` (8 by default) file
    # downloads at once, and every worker thread calls update() on these
    # same bar instances from its own thread. The accounting in
    # _progress_class does a read-modify-write (bump `seen[key]`, recompute
    # `max`, compare-and-set `emitted`) that is only correct under a lock:
    # without one, two threads can both read a stale `emitted`, both pass
    # the guard, and both emit — reintroducing the double-counting the
    # previous fix removed, just non-deterministically instead of always.
    #
    # This is a probabilistic regression test, not a proof of thread safety.
    # An unlucky interleaving could still slip through on any single run.
    # To make a real regression likely to be caught, it uses a realistic
    # thread count (8, matching the library's default max_workers) split
    # unevenly across two bars (5 vs 3) so summing instead of taking the max
    # would visibly overshoot, enough updates per thread (1000, so 8000
    # total update() calls funneled through one lock) to make concurrent
    # read-modify-write windows likely to overlap, AND a much shorter GIL
    # switch interval for the duration of the test. Verified empirically
    # (10 runs each, not part of this test) that without the switch-interval
    # change the pre-lock code passed all 5 spot-checks run by hand — the
    # default 5ms interval rarely lands a switch inside this short a race
    # window on this box. At a 1us interval the pre-lock code failed 10/10
    # and the locked code passed 10/10, so that is the interval used here.
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        byte_events = []
        cls = _progress_class(on_bytes=byte_events.append)

        bar_a = cls(total=10_000, unit="B", file=io.StringIO())
        bar_b = cls(total=10_000, unit="B", file=io.StringIO())

        iterations = 1000
        threads = (
            [threading.Thread(target=lambda: [bar_a.update(1) for _ in range(iterations)])
             for _ in range(5)]
            + [threading.Thread(target=lambda: [bar_b.update(1) for _ in range(iterations)])
               for _ in range(3)]
        )

        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    expected = max(5 * iterations, 3 * iterations)   # 5000, not 5000+3000=8000
    assert sum(byte_events) == expected


def test_fake_commit_records_what_it_was_handed(tmp_path):
    c = FakeHFClient()
    sha = c.commit("a/b", "main", [("labels/1.txt", str(tmp_path / "1.txt"))],
                   ["images/2.jpg"], "msg", parent_commit="oldsha")
    assert c.commits[0]["adds"] == [("labels/1.txt", str(tmp_path / "1.txt"))]
    assert c.commits[0]["deletes"] == ["images/2.jpg"]
    assert c.commits[0]["parent_commit"] == "oldsha"
    assert isinstance(sha, str) and sha


def test_fake_commit_can_raise_conflict():
    from app.hf.client import HFConflict
    c = FakeHFClient(raises=HFConflict("precondition failed"))
    with pytest.raises(HFConflict):
        c.commit("a/b", "main", [], [], "msg", parent_commit="x")


def test_conflict_is_an_hferror():
    """So a caller that handles HFError does not miss a 412."""
    from app.hf.client import HFConflict, HFError
    assert issubclass(HFConflict, HFError)


def test_progress_bars_do_not_render_to_the_console(capfd):
    """Rendered bars have no consumer and bury real tracebacks in the logs.

    Must NOT be fixed with disable=True: tqdm then never sets `unit`, silently
    breaking the byte/file routing everything else depends on.
    """
    cls = _progress_class(on_bytes=lambda n: None)
    bar = cls(total=100, unit="B")
    bar.update(50)
    bar.close()
    out, err = capfd.readouterr()
    assert out == "" and err == ""
    assert bar.unit == "B"        # proves disable=True was not used
