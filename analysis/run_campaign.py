#!/usr/bin/env python3
"""Production campaign launcher, slice-major scheduler, and integrity monitor.

Orchestrates the 6 x 1,760 = 10,560 factorial sweep runs across Cell1_Sweep..Cell6_Sweep:
- Queries run numbers and iteration variables directly from OMNeT++ (`opp_run -q runs`).
- Verifies that `libmatrixfactory.so` is fresh against `src/` and matches `--expected-lib-sha256`.
- Orders execution slice-major `(nAmr, telInterval, phyRate)` with migration-boundary slices
  first, completing all 6 cells and all repetitions of a slice before advancing.
- Supports slice-level sharding (`--shard i/M`), Phase 5b 96-run dry-run corners
  (`--dry-run-corners`), and repetition top-ups (`--repeat` / `--max-reps`).
- Enforces the Phase 5a retry and completion contract: validates every `.sca` via
  `export_lookup.parse_sca_file` and `parse_sca_statistics`, deletes `.vec`/`.vci` files,
  records uncompressed `.sca` size and SHA-256 in `manifest.csv`, compresses `.sca` to
  `.sca.gz`, retries a failed run number at most once (never substituting a seed), and
  halts immediately if a run fails twice or if free disk space drops below `--min-free-gb`.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import gzip
import hashlib
import logging
import os
import re
import shutil
import socket
import threading
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deadline_metrics as dm  # noqa: E402
import export_lookup as ex  # noqa: E402
from env_config import (  # noqa: E402
    INET_ROOT_STR as INET_ROOT,
    MATRIXFACTORY_LIB_STR as MATRIXFACTORY_LIB,
    OMNETPP_ENV_STR as OMNETPP_ENV,
    PROJECT_ROOT_STR as PROJECT_ROOT,
    SIM_DIR_STR as SIM_DIR,
    assert_library_fresh,
)

LOG = logging.getLogger("run_campaign")

CELLS = (1, 2, 3, 4, 5, 6)
PRIORITY_NAMRS = (80, 40, 20, 10, 5)
PRIORITY_TEL_INTERVALS = ("300us", "407us", "472us", "527us", "600us", "747us", "996us", "2000us")
PRIORITY_PHYS = (12, 54)

CORNER_NAMRS = {5, 80}
CORNER_PHYS = {12, 54}
CORNER_TELS = {"2000us", "300us"}
CORNER_REPS = {0, 1}

MANIFEST_COLUMNS = [
    "cell",
    "nAmr",
    "phy",
    "telInterval",
    "rep",
    "run_number",
    "host",
    "start_time",
    "wall_seconds",
    "exit_code",
    "max_rss_kb",
    "sca_bytes",
    "sca_sha256",
    "library_sha256",
]

_RUN_LINE_RE = re.compile(
    r"^Run\s+(\d+):\s+\$nAmr=(\d+),\s+\$nSta=(\d+),\s+\$phyRate=(\d+)Mbps,\s+\$telInterval=([0-9]+us),\s+\$repetition=(\d+)\s*$"
)


@dataclasses.dataclass(frozen=True)
class RunSpec:
    cell: int
    run_number: int
    n_amr: int
    phy_rate_mbps: int
    tel_interval: str
    rep: int

    @property
    def config_name(self) -> str:
        return f"Cell{self.cell}_Sweep"

    @property
    def slice_key(self) -> Tuple[int, str, int]:
        return (self.n_amr, self.tel_interval, self.phy_rate_mbps)

    def base_stem(self, n_sta: int = 4) -> str:
        return (
            f"{self.config_name}-nAmr={self.n_amr},nSta={n_sta},"
            f"phyRate={self.phy_rate_mbps}Mbps,telInterval={self.tel_interval}-#{self.rep}"
        )

    def sca_path(self, out_dir: Path) -> Path:
        return Path(out_dir) / f"{self.base_stem()}.sca"

    def sca_gz_path(self, out_dir: Path) -> Path:
        return Path(out_dir) / f"{self.base_stem()}.sca.gz"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_library_gate(
    lib_path: Path = Path(PROJECT_ROOT) / "libmatrixfactory.so",
    expected_sha256: Optional[str] = None,
) -> str:
    """Verify that libmatrixfactory.so exists, is newer than src/*, and matches expected_sha256."""
    if lib_path == Path(PROJECT_ROOT) / "libmatrixfactory.so":
        assert_library_fresh()
    elif not Path(lib_path).exists():
        raise FileNotFoundError(f"Shared library not found: {lib_path}")
    actual = sha256_file(Path(lib_path))
    if expected_sha256 and actual.lower() != expected_sha256.strip().lower():
        raise RuntimeError(
            f"libmatrixfactory.so SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return actual


def check_disk_space(target_dir: Path, min_free_gb: float = 2.0) -> float:
    """Return free GiB in target_dir; raise RuntimeError if below min_free_gb."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target_dir)
    free_gb = usage.free / (1024.0**3)
    if free_gb < float(min_free_gb):
        raise RuntimeError(
            f"Free disk space on {target_dir} is {free_gb:.2f} GiB, below threshold {min_free_gb:.2f} GiB"
        )
    return free_gb


def parse_runs_output(cell: int, text: str) -> List[RunSpec]:
    """Parse `opp_run -q runs -c CellN_Sweep` output into RunSpec entries."""
    specs: List[RunSpec] = []
    for raw in text.splitlines():
        m = _RUN_LINE_RE.match(raw.strip())
        if not m:
            continue
        run_num, n_amr, _n_sta, phy, tel, rep = m.groups()
        if tel not in ex.TEL_INTERVAL_TO_MBPS:
            raise RuntimeError(f"Unmapped telInterval {tel!r} in run query for Cell{cell}_Sweep")
        specs.append(
            RunSpec(
                cell=int(cell),
                run_number=int(run_num),
                n_amr=int(n_amr),
                phy_rate_mbps=int(phy),
                tel_interval=tel,
                rep=int(rep),
            )
        )
    return specs


def enumerate_cell_runs(cell: int, repeat: int = 22) -> List[RunSpec]:
    """Query OMNeT++ for all run numbers and parameters of Cell<cell>_Sweep."""
    config = f"Cell{cell}_Sweep"
    repeat_arg = f"'--repeat={repeat}'" if repeat != 22 else ""
    cmd_runs = (
        f"source {OMNETPP_ENV} && export INET_ROOT={INET_ROOT} && cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. -l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-q runs -c {config} omnetpp.ini {repeat_arg}"
    )
    res_runs = subprocess.run(["bash", "-c", cmd_runs], capture_output=True, text=True)
    if res_runs.returncode != 0:
        raise RuntimeError(f"Failed to query runs for {config}:\n{res_runs.stderr}\n{res_runs.stdout}")

    cmd_nums = (
        f"source {OMNETPP_ENV} && export INET_ROOT={INET_ROOT} && cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. -l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-q runnumbers -c {config} omnetpp.ini {repeat_arg}"
    )
    res_nums = subprocess.run(["bash", "-c", cmd_nums], capture_output=True, text=True)
    if res_nums.returncode != 0:
        raise RuntimeError(f"Failed to query runnumbers for {config}:\n{res_nums.stderr}")

    specs = parse_runs_output(cell, res_runs.stdout)
    expected_count = 80 * int(repeat)
    if len(specs) != expected_count:
        raise RuntimeError(f"{config}: expected {expected_count} runs from -q runs, got {len(specs)}")

    # Verify that -q runnumbers contains the exact 0..expected_count-1 sequence
    num_tokens = [
        int(tok)
        for line in res_nums.stdout.splitlines()
        if not line.startswith(("Activating", "Environment", "OMNeT++", "Version:", "See the", "Setting", "Config:", "Number"))
        for tok in line.split()
        if tok.isdigit()
    ]
    if num_tokens != list(range(expected_count)):
        raise RuntimeError(f"{config}: -q runnumbers did not match 0..{expected_count - 1}")
    return specs


def order_runs_slice_major(
    specs: Sequence[RunSpec],
    *,
    dry_run_corners: bool = False,
    max_reps: Optional[int] = None,
    shard: Optional[Tuple[int, int]] = None,
) -> List[RunSpec]:
    """Order runs slice-major (all 6 cells and all reps of a slice together), priority slices first."""
    filtered: List[RunSpec] = []
    for s in specs:
        if dry_run_corners:
            if (
                s.n_amr not in CORNER_NAMRS
                or s.phy_rate_mbps not in CORNER_PHYS
                or s.tel_interval not in CORNER_TELS
                or s.rep not in CORNER_REPS
            ):
                continue
        if max_reps is not None and s.rep >= int(max_reps):
            continue
        filtered.append(s)

    namr_rank = {v: i for i, v in enumerate(PRIORITY_NAMRS)}
    tel_rank = {v: i for i, v in enumerate(PRIORITY_TEL_INTERVALS)}
    phy_rank = {v: i for i, v in enumerate(PRIORITY_PHYS)}

    by_slice: Dict[Tuple[int, str, int], List[RunSpec]] = {}
    for s in filtered:
        by_slice.setdefault(s.slice_key, []).append(s)

    ordered_slices = sorted(
        by_slice.keys(),
        key=lambda k: (namr_rank.get(k[0], 99), tel_rank.get(k[1], 99), phy_rank.get(k[2], 99)),
    )

    if shard is not None:
        shard_idx, shard_total = shard
        if not (1 <= shard_idx <= shard_total):
            raise ValueError(f"Invalid shard {shard_idx}/{shard_total}: require 1 <= i <= M")
        ordered_slices = ordered_slices[(shard_idx - 1) :: shard_total]

    result: List[RunSpec] = []
    for sk in ordered_slices:
        slice_runs = sorted(by_slice[sk], key=lambda r: (r.rep, r.cell))
        result.extend(slice_runs)
    return result


def validate_sca_file(sca_path: Path, spec: Optional[RunSpec] = None) -> None:
    """Validate that a .sca or .sca.gz file is complete, conserves packets, and has domain statistics."""
    path = Path(sca_path)
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Missing or empty scalar file: {path}")

    attrs, scalars = ex.parse_sca_file(path)
    stats = ex.parse_sca_statistics(path)

    if spec is not None:
        key = ex._run_key(attrs, path)
        expected_key = (
            spec.cell,
            spec.n_amr,
            ex.TEL_INTERVAL_TO_MBPS[spec.tel_interval],
            spec.phy_rate_mbps,
            spec.rep,
        )
        if key != expected_key:
            raise RuntimeError(f"{path.name}: header key {key} does not match expected {expected_key}")

    coord_mods = sorted({mod for (mod, sname) in scalars if sname == "n_generated_valid_orders"})
    if len(coord_mods) != 1:
        raise RuntimeError(f"{path.name}: expected 1 ExperimentCoordinator, found {len(coord_mods)}")
    cmod = coord_mods[0]

    for cls in dm.CLASSES:
        req = [
            f"n_generated_valid_{cls}",
            f"n_delivered_valid_{cls}",
            f"n_drop_queue_{cls}",
            f"n_drop_retry_{cls}",
            f"n_drop_other_{cls}",
            f"n_late_termination_{cls}",
        ]
        for sname in req:
            if (cmod, sname) not in scalars:
                raise RuntimeError(f"{path.name}: missing required coordinator scalar {sname}")
        gen = int(round(scalars[(cmod, f"n_generated_valid_{cls}")]))
        deliv = int(round(scalars[(cmod, f"n_delivered_valid_{cls}")]))
        dq = int(round(scalars[(cmod, f"n_drop_queue_{cls}")]))
        dr = int(round(scalars[(cmod, f"n_drop_retry_{cls}")]))
        do = int(round(scalars[(cmod, f"n_drop_other_{cls}")]))
        lt = int(round(scalars[(cmod, f"n_late_termination_{cls}")]))
        if gen != deliv + dq + dr + do + lt:
            raise RuntimeError(
                f"{path.name} ({cls}): coordinator conservation violated: "
                f"{gen} != {deliv} + {dq} + {dr} + {do} + {lt}"
            )
        sinks = ex.class_sink_modules(scalars, cls)
        if not sinks:
            raise RuntimeError(f"{path.name}: no DeadlineSink found for class {cls}")
        for domain_stat in ex.DOMAIN_STATS.values():
            missing = [m for m in sinks if "count" not in stats.get((m, domain_stat), {})
                       or "mean" not in stats.get((m, domain_stat), {})]
            if missing:
                raise RuntimeError(
                    f"{path.name} ({cls}): domain statistic {domain_stat} missing on {len(missing)} of "
                    f"{len(sinks)} sink(s), e.g. {missing[0]}")


def cleanup_auxiliary_files(out_dir: Path, spec: RunSpec) -> None:
    """Remove .vec, .vci, and .elog files for a completed or failed run."""
    stem = spec.base_stem()
    for suffix in (".vec", ".vci", ".elog"):
        aux = Path(out_dir) / f"{stem}{suffix}"
        if aux.exists():
            aux.unlink()


def compress_sca_file(sca_path: Path) -> Path:
    """Gzip a validated .sca file in-place to .sca.gz and remove the uncompressed .sca."""
    gz_path = Path(f"{sca_path}.gz")
    tmp_gz = Path(f"{sca_path}.gz.tmp")
    with open(sca_path, "rb") as f_in, gzip.open(tmp_gz, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    tmp_gz.replace(gz_path)
    sca_path.unlink()
    return gz_path


def find_existing_valid_output(out_dir: Path, spec: RunSpec) -> Optional[Path]:
    """Return the existing .sca.gz or .sca path if present and valid; delete corrupt partials."""
    gz_path = spec.sca_gz_path(out_dir)
    sca_path = spec.sca_path(out_dir)
    for candidate in (gz_path, sca_path):
        if candidate.exists():
            try:
                validate_sca_file(candidate, spec)
                # Ensure no duplicate plain + gz pair remains
                if candidate == gz_path and sca_path.exists():
                    sca_path.unlink()
                return candidate
            except Exception as exc:
                LOG.warning("Removing corrupt/incomplete output %s (%s)", candidate.name, exc)
                candidate.unlink(missing_ok=True)
    return None


_MANIFEST_LOCK = threading.Lock()


def append_manifest_row(manifest_path: Path, row: Dict[str, object]) -> None:
    """Append one row; serialized so concurrent workers cannot write a second header or interleave rows."""
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with _MANIFEST_LOCK:
        write_header = not manifest_path.exists() or manifest_path.stat().st_size == 0
        with open(manifest_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
            if write_header:
                writer.writeheader()
            writer.writerow({k: row[k] for k in MANIFEST_COLUMNS})


def default_runner(spec: RunSpec, out_dir: Path, log_path: Path, sim_time_limit: Optional[str] = None) -> Tuple[int, int]:
    """Run one OMNeT++ simulation and return (exit_code, max_rss_kb)."""
    time_override = f"'--sim-time-limit={sim_time_limit}' '--**.simTimeLimit={sim_time_limit}'" if sim_time_limit else ""
    cmd = (
        f"source {OMNETPP_ENV} && export INET_ROOT={INET_ROOT} && cd {SIM_DIR} && "
        f"/usr/bin/time -f 'MAX_RSS_KB=%M' "
        f"opp_run -n $INET_ROOT/src:../src:. -l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-u Cmdenv -c {spec.config_name} -r {spec.run_number} omnetpp.ini "
        f"'--result-dir={out_dir.resolve()}' {time_override}"
    )
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    combined = (res.stdout or "") + "\n" + (res.stderr or "")
    log_path.write_text(combined, encoding="utf-8")

    max_rss = 0
    for line in combined.splitlines():
        if line.startswith("MAX_RSS_KB="):
            try:
                max_rss = int(line.split("=", 1)[1].strip())
            except ValueError:
                pass
    if "<!> Error" in combined or "cRuntimeError" in combined:
        return (res.returncode or 1), max_rss
    return res.returncode, max_rss


def execute_run_with_retry(
    spec: RunSpec,
    *,
    out_dir: Path,
    manifest_path: Path,
    log_dir: Path,
    lib_sha256: str,
    compress: bool = True,
    min_free_gb: float = 2.0,
    sim_time_limit: Optional[str] = None,
    runner: Optional[Callable[[RunSpec, Path, Path, Optional[str]], Tuple[int, int]]] = None,
) -> Dict[str, object]:
    """Execute one RunSpec with resumability and at most 1 retry of the exact same run_number."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = find_existing_valid_output(out_dir, spec)
    if existing is not None:
        return {"status": "skipped", "path": existing, "spec": spec}

    run_fn = runner or default_runner
    host = socket.gethostname()
    last_error: Optional[Exception] = None

    for attempt in (1, 2):
        check_disk_space(out_dir, min_free_gb=min_free_gb)
        # Clean any stale partial files before starting the attempt
        spec.sca_path(out_dir).unlink(missing_ok=True)
        spec.sca_gz_path(out_dir).unlink(missing_ok=True)
        cleanup_auxiliary_files(out_dir, spec)

        start_utc = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        t0 = time.monotonic()
        log_path = Path(log_dir) / f"{spec.config_name}_run{spec.run_number}_attempt{attempt}.log"
        rc, max_rss_kb = run_fn(spec, out_dir, log_path, sim_time_limit)
        wall_s = round(time.monotonic() - t0, 3)
        cleanup_auxiliary_files(out_dir, spec)

        sca_path = spec.sca_path(out_dir)
        try:
            if rc != 0:
                raise RuntimeError(f"exit code {rc}")
            validate_sca_file(sca_path, spec)
            sca_bytes = sca_path.stat().st_size
            sca_hash = sha256_file(sca_path)
            final_path = compress_sca_file(sca_path) if compress else sca_path
            if compress:
                validate_sca_file(final_path, spec)

            row = {
                "cell": spec.cell,
                "nAmr": spec.n_amr,
                "phy": spec.phy_rate_mbps,
                "telInterval": spec.tel_interval,
                "rep": spec.rep,
                "run_number": spec.run_number,
                "host": host,
                "start_time": start_utc,
                "wall_seconds": wall_s,
                "exit_code": 0,
                "max_rss_kb": max_rss_kb,
                "sca_bytes": sca_bytes,
                "sca_sha256": sca_hash,
                "library_sha256": lib_sha256,
            }
            append_manifest_row(manifest_path, row)
            return {"status": "completed", "path": final_path, "row": row, "attempts": attempt}
        except Exception as exc:
            last_error = exc
            sca_path.unlink(missing_ok=True)
            spec.sca_gz_path(out_dir).unlink(missing_ok=True)
            fail_row = {
                "cell": spec.cell,
                "nAmr": spec.n_amr,
                "phy": spec.phy_rate_mbps,
                "telInterval": spec.tel_interval,
                "rep": spec.rep,
                "run_number": spec.run_number,
                "host": host,
                "start_time": start_utc,
                "wall_seconds": wall_s,
                "exit_code": rc if rc != 0 else 1,
                "max_rss_kb": max_rss_kb,
                "sca_bytes": 0,
                "sca_sha256": "",
                "library_sha256": lib_sha256,
            }
            append_manifest_row(manifest_path, fail_row)
            LOG.error(
                "Attempt %d/2 failed for %s run %d (N=%d, PHY=%d, tel=%s, rep=%d): %s",
                attempt,
                spec.config_name,
                spec.run_number,
                spec.n_amr,
                spec.phy_rate_mbps,
                spec.tel_interval,
                spec.rep,
                exc,
            )

    raise RuntimeError(
        f"Campaign halted: {spec.config_name} run {spec.run_number} "
        f"(N={spec.n_amr}, PHY={spec.phy_rate_mbps}, tel={spec.tel_interval}, rep={spec.rep}) "
        f"failed twice: {last_error}"
    )


def run_slice_parallel(
    slice_specs: Sequence[RunSpec],
    workers: int,
    run_one: Callable[[RunSpec], Dict[str, object]],
) -> List[Dict[str, object]]:
    """Run one slice on a thread pool. On the first failure, drop every queued run, let the runs already
    in flight finish (so the manifest stays consistent), then re-raise. Leaving the pool via ``with``
    would instead run the whole remaining slice (up to 131 runs) before the error surfaced."""
    results: List[Dict[str, object]] = []
    pool = ThreadPoolExecutor(max_workers=int(workers))
    try:
        futs = [pool.submit(run_one, spec) for spec in slice_specs]
        for fut in as_completed(futs):
            results.append(fut.result())
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return results


def parse_shard_arg(shard_str: Optional[str]) -> Optional[Tuple[int, int]]:
    if not shard_str:
        return None
    parts = shard_str.strip().split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"Invalid --shard {shard_str!r}; expected 'i/M' (e.g. '1/4')")
    i, m = int(parts[0]), int(parts[1])
    if not (1 <= i <= m):
        raise ValueError(f"Invalid --shard {shard_str!r}; require 1 <= i <= M")
    return (i, m)


def main(argv: Optional[Sequence[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out-dir", default=str(Path(SIM_DIR) / "results" / "campaign"),
                   help="directory for campaign .sca / .sca.gz outputs")
    p.add_argument("--evidence-dir", default=str(Path(PROJECT_ROOT) / "evidence" / "05_campaign"),
                   help="directory for manifest.csv and per-run logs/")
    p.add_argument("--expected-lib-sha256", default=None,
                   help="require libmatrixfactory.so to match this SHA-256 before launching")
    p.add_argument("--workers", type=int, default=2,
                   help="concurrent worker processes (size from available RAM, default 2)")
    p.add_argument("--repeat", type=int, default=22,
                   help="repetitions per point configured in OMNeT++ (default 22)")
    p.add_argument("--max-reps", type=int, default=None,
                   help="optional cap on repetition index (e.g. 2 for quick tests)")
    p.add_argument("--dry-run-corners", action="store_true",
                   help="run only the 96-run Phase 5b corner grid (N in {5,80}, PHY in {54,12}, load in {2000us,300us}, 6 cells, 2 reps)")
    p.add_argument("--shard", default=None,
                   help="slice-level shard 'i/M' (1-indexed, e.g. '1/3'); never splits a 6-cell slice")
    p.add_argument("--no-gzip", action="store_true",
                   help="keep plain .sca files instead of compressing to .sca.gz")
    p.add_argument("--min-free-gb", type=float, default=2.0,
                   help="halt campaign if free disk space on --out-dir falls below this GiB threshold")
    p.add_argument("--sim-time-limit", default=None,
                   help="optional override for sim-time-limit (for testing only)")
    p.add_argument("--list-only", action="store_true",
                   help="enumerate and print the slice-major schedule summary without running simulations")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    lib_sha = check_library_gate(expected_sha256=args.expected_lib_sha256)
    LOG.info("Verified libmatrixfactory.so (SHA-256: %s)", lib_sha)

    all_specs: List[RunSpec] = []
    for c in CELLS:
        cell_specs = enumerate_cell_runs(c, repeat=args.repeat)
        all_specs.extend(cell_specs)
    LOG.info("Enumerated %d total runs across %d cells", len(all_specs), len(CELLS))

    shard = parse_shard_arg(args.shard)
    scheduled = order_runs_slice_major(
        all_specs,
        dry_run_corners=args.dry_run_corners,
        max_reps=args.max_reps,
        shard=shard,
    )
    n_slices = len({s.slice_key for s in scheduled})
    LOG.info("Scheduled %d runs across %d slices (slice-major order)", len(scheduled), n_slices)

    if args.list_only:
        return

    out_dir = Path(args.out_dir)
    ev_dir = Path(args.evidence_dir)
    manifest_path = ev_dir / "manifest.csv"
    log_dir = ev_dir / "logs"

    completed = 0
    skipped = 0
    if int(args.workers) <= 1:
        for idx, spec in enumerate(scheduled, 1):
            res = execute_run_with_retry(
                spec,
                out_dir=out_dir,
                manifest_path=manifest_path,
                log_dir=log_dir,
                lib_sha256=lib_sha,
                compress=not args.no_gzip,
                min_free_gb=args.min_free_gb,
                sim_time_limit=args.sim_time_limit,
            )
            if res["status"] == "skipped":
                skipped += 1
            else:
                completed += 1
                LOG.info("[%d/%d] %s run %d finished in %.1fs", idx, len(scheduled), spec.config_name, spec.run_number, res["row"]["wall_seconds"])
    else:
        # Process slice by slice so slice-major completion order is preserved even with parallel workers
        slices_in_order: List[Tuple[int, str, int]] = []
        seen = set()
        for s in scheduled:
            if s.slice_key not in seen:
                seen.add(s.slice_key)
                slices_in_order.append(s.slice_key)

        for s_idx, sk in enumerate(slices_in_order, 1):
            slice_specs = [s for s in scheduled if s.slice_key == sk]
            slice_results = run_slice_parallel(
                slice_specs,
                int(args.workers),
                lambda spec: execute_run_with_retry(
                    spec,
                    out_dir=out_dir,
                    manifest_path=manifest_path,
                    log_dir=log_dir,
                    lib_sha256=lib_sha,
                    compress=not args.no_gzip,
                    min_free_gb=args.min_free_gb,
                    sim_time_limit=args.sim_time_limit,
                ),
            )
            for res in slice_results:
                if res["status"] == "skipped":
                    skipped += 1
                else:
                    completed += 1
            LOG.info("Completed slice %d/%d %s (completed=%d, skipped=%d)", s_idx, len(slices_in_order), sk, completed, skipped)

    LOG.info("Campaign pass finished cleanly: completed=%d, skipped=%d", completed, skipped)


if __name__ == "__main__":
    main()
