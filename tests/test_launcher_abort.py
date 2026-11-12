"""Interrupt, termination and dirty-tree behaviour of analysis/run_campaign.py.

Each simulation runs in its own session (so a timeout can kill its process group). That means a terminal
Ctrl-C or a plain `kill` does not reach it; these tests pin down that the launcher cleans up after itself.
Process counting matches the exact command line, so the tests cannot match (or kill) themselves.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import run_campaign as rc  # noqa: E402


def alive(marker: str) -> int:
    lines = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout.splitlines()
    return sum(1 for line in lines if line.startswith(f"sleep {marker}"))


def wait_for(marker: str, count: int, seconds: float = 8.0) -> None:
    deadline = time.time() + seconds
    while alive(marker) < count and time.time() < deadline:
        time.sleep(0.05)
    assert alive(marker) >= count, f"expected {count} live 'sleep {marker}' processes"


def spec(i: int) -> "rc.RunSpec":
    return rc.RunSpec(cell=1, run_number=i, n_amr=5, phy_rate_mbps=54, tel_interval="2000us", rep=i)


@pytest.fixture(autouse=True)
def clean_abort_state():
    rc.reset_abort_state()
    yield
    rc.abort_all_runs()  # never leave a stray simulation behind, even if a test fails
    rc.reset_abort_state()


def test_abort_all_runs_kills_the_whole_live_process_group(tmp_path):
    result = {}
    worker = threading.Thread(
        target=lambda: result.update(
            r=rc.run_subprocess_wait4(["bash", "-c", "sleep 61.1 & sleep 61.1 & wait"], tmp_path / "a.log", timeout_sec=120)))
    worker.start()
    wait_for("61.1", 2)
    assert rc.abort_all_runs() == 1
    worker.join(10)
    assert not worker.is_alive()
    assert alive("61.1") == 0


def test_no_attempt_starts_once_the_campaign_is_aborted(tmp_path):
    calls = []
    rc.abort_all_runs()
    with pytest.raises(rc.CampaignAborted):
        rc.execute_run_with_retry(
            spec(0), out_dir=tmp_path / "o", manifest_path=tmp_path / "m.csv", log_dir=tmp_path / "l",
            lib_sha256="ab" * 32, git_head="h", git_dirty=False,
            runner=lambda *a, **k: calls.append(1) or (0, 1))
    assert calls == []


def test_a_run_killed_by_abort_is_not_recorded_as_a_failure_and_not_retried(tmp_path):
    calls = []

    def runner(spec_, out_dir, log_path, sim_time_limit):
        calls.append(1)
        rc.abort_all_runs()  # the launcher is interrupted while this run is in flight
        return -9, 1

    manifest = tmp_path / "m.csv"
    with pytest.raises(rc.CampaignAborted):
        rc.execute_run_with_retry(
            spec(0), out_dir=tmp_path / "o", manifest_path=manifest, log_dir=tmp_path / "l",
            lib_sha256="ab" * 32, git_head="h", git_dirty=False, runner=runner)
    assert calls == [1]  # no second attempt
    assert not manifest.exists()  # no failure row for a run we killed ourselves


def test_interrupt_in_a_slice_kills_the_runs_in_flight_and_returns_promptly(tmp_path):
    def run_one(s):
        if s.run_number == 0:
            wait_for("61.2", 2)  # the other two simulations are live
            raise KeyboardInterrupt  # then behave as an interrupted launcher
        rc.run_subprocess_wait4(["sleep", "61.2"], tmp_path / f"r{s.run_number}.log", timeout_sec=120)
        return {"status": "completed"}

    t0 = time.time()
    with pytest.raises(KeyboardInterrupt):
        rc.run_slice_parallel([spec(0), spec(1), spec(2)], 3, run_one)
    assert time.time() - t0 < 20, "the slice waited out the in-flight simulations"
    assert alive("61.2") == 0


def test_signal_during_wait_kills_the_child_in_the_single_worker_path(tmp_path):
    killer = threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGINT))
    killer.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            rc.run_subprocess_wait4(["sleep", "61.3"], tmp_path / "s.log", timeout_sec=120)
    finally:
        killer.cancel()
    time.sleep(0.3)
    assert alive("61.3") == 0


def test_sigterm_becomes_a_clean_exit_so_cleanup_runs():
    with pytest.raises(SystemExit) as exc:
        rc._raise_exit_on_signal(signal.SIGTERM, None)
    assert exc.value.code == 128 + signal.SIGTERM


def test_pinned_launch_refuses_a_dirty_tree_unless_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "get_git_state", lambda *a, **k: ("abc123", True))
    monkeypatch.setattr(rc, "check_library_gate", lambda *a, **k: "ab" * 32)
    monkeypatch.setattr(rc, "enumerate_cell_runs", lambda cell, repeat=22: [])
    base = ["--expected-lib-sha256", "ab" * 32, "--out-dir", str(tmp_path / "o"), "--evidence-dir", str(tmp_path / "e")]
    old = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(RuntimeError, match="uncommitted changes"):
            rc.main(base)
        rc.main(base + ["--allow-dirty"])  # explicit override proceeds (nothing to run here)
        rc.main(["--allow-unpinned-lib", "--out-dir", str(tmp_path / "o"), "--evidence-dir", str(tmp_path / "e")])
    finally:
        signal.signal(signal.SIGTERM, old)
