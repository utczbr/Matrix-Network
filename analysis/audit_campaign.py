#!/usr/bin/env python3
"""Independent Phase 6 completeness, conservation, and stage-snapshot auditor for Matrix .sca(.gz) outputs.

Uses only the Python standard library and implements an independent OMNeT++ scalar parser
without importing analysis/export_lookup.py or analysis/deadline_metrics.py.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

CLASSES = ("orders", "dds", "state", "telemetry")
ALL_CELLS = (1, 2, 3, 4, 5, 6)
CSMA_CELLS = {1, 3, 5}
SCHED_CELLS = {2, 4, 6}
ALL_NAMRS = (5, 10, 20, 40, 80)
ALL_PHYS = (12, 54)
ALL_TELS = ("300us", "407us", "472us", "527us", "600us", "747us", "996us", "2000us")

FNAME_RE = re.compile(
    r"^Cell(?P<cell>[1-6])_Sweep-nAmr=(?P<namr>\d+),nSta=\d+,"
    r"phyRate=(?P<phy>\d+)Mbps,telInterval=(?P<tel>\d+us)-#(?P<rep>\d+)\.sca(?:\.gz)?$"
)
AMR_ORDER_SINK_RE = re.compile(r"^MatrixFactoryNetwork\.amr\[(\d+)\]\.app\[1\]\.sink$")


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        return token[1:-1].replace('\\"', '"')
    return token


def _split_sca_tokens(line: str) -> List[str]:
    """Parse whitespace-delimited OMNeT++ .sca tokens preserving double-quoted fields."""
    if '"' not in line and "\\" not in line:
        return line.split()
    tokens: List[str] = []
    i = 0
    n = len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        if line[i] == '"':
            j = i + 1
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if line[j] == '"':
                    j += 1
                    break
                j += 1
            tokens.append(_unquote(line[i:j]))
            i = j
        else:
            j = i
            while j < n and not line[j].isspace():
                j += 1
            tokens.append(line[i:j])
            i = j
    return tokens


def _open_sca(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "rt", encoding="utf-8", errors="replace")


def parse_sca_header(path: Path) -> Dict[str, object]:
    """Read only header attrs/itervars from an OMNeT++ .sca(.gz) file."""
    attrs: Dict[str, str] = {}
    itervars: Dict[str, str] = {}
    run_id = ""
    with _open_sca(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("version "):
                continue
            if line.startswith(("scalar ", "statistic ", "vector ", "bin ")):
                break
            toks = _split_sca_tokens(line)
            if not toks:
                continue
            tag = toks[0]
            if tag == "run" and len(toks) >= 2:
                run_id = toks[1]
            elif tag == "attr" and len(toks) >= 3:
                attrs[toks[1]] = " ".join(toks[2:])
            elif tag == "itervar" and len(toks) >= 3:
                itervars[toks[1]] = " ".join(toks[2:])
    if "configname" not in attrs or "repetition" not in attrs:
        raise ValueError(f"{path}: missing required configname/repetition header attrs")
    cfg = str(attrs["configname"])
    m_cfg = re.match(r"^Cell([1-6])_Sweep$", cfg)
    if not m_cfg:
        raise ValueError(f"{path}: unexpected configname {cfg!r}")
    cell = int(m_cfg.group(1))
    rep = int(attrs["repetition"])
    run_number = int(attrs["runnumber"]) if "runnumber" in attrs else -1
    namr_raw = itervars.get("nAmr") or attrs.get("nAmr")
    phy_raw = itervars.get("phyRate") or attrs.get("phyRate")
    tel_raw = itervars.get("telInterval") or attrs.get("telInterval")
    if namr_raw is None or phy_raw is None or tel_raw is None:
        raise ValueError(f"{path}: missing nAmr/phyRate/telInterval in header")
    namr = int(namr_raw)
    phy = int(str(phy_raw).replace("Mbps", ""))
    tel = str(tel_raw)

    m_name = FNAME_RE.match(path.name)
    if m_name:
        if (
            int(m_name.group("cell")) != cell
            or int(m_name.group("namr")) != namr
            or int(m_name.group("phy")) != phy
            or m_name.group("tel") != tel
            or int(m_name.group("rep")) != rep
        ):
            raise ValueError(f"{path}: filename metadata disagrees with .sca header")

    return {
        "path": path,
        "run_id": run_id,
        "cell": cell,
        "nAmr": namr,
        "phy": phy,
        "telInterval": tel,
        "rep": rep,
        "run_number": run_number,
        "key": (cell, namr, phy, tel, rep),
    }


def parse_sca_full(path: Path) -> Dict[str, object]:
    """Independently parse header, scalars, and statistic fields from a single .sca(.gz) file."""
    attrs: Dict[str, str] = {}
    itervars: Dict[str, str] = {}
    scalars: Dict[Tuple[str, str], float] = {}
    stats: Dict[Tuple[str, str], Dict[str, float]] = {}
    cur_stat: Optional[Tuple[str, str]] = None

    with _open_sca(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("version "):
                continue
            toks = _split_sca_tokens(line)
            if not toks:
                continue
            tag = toks[0]
            if tag == "attr" and len(toks) >= 3:
                cur_stat = None
                attrs[toks[1]] = " ".join(toks[2:])
            elif tag == "itervar" and len(toks) >= 3:
                cur_stat = None
                itervars[toks[1]] = " ".join(toks[2:])
            elif tag == "scalar" and len(toks) >= 4:
                cur_stat = None
                scalars[(toks[1], toks[2])] = float(toks[3])
            elif tag == "statistic" and len(toks) >= 3:
                cur_stat = (toks[1], toks[2])
                stats.setdefault(cur_stat, {})
            elif tag == "field" and len(toks) >= 3 and cur_stat is not None:
                stats[cur_stat][toks[1]] = float(toks[2])
            elif tag != "bin":
                cur_stat = None

    return {
        "attrs": attrs,
        "itervars": itervars,
        "scalars": scalars,
        "stats": stats,
    }


def _sink_class(module: str) -> Optional[str]:
    if module == "MatrixFactoryNetwork.fms.app[0].sink":
        return "state"
    if module == "MatrixFactoryNetwork.fms.app[1].sink":
        return "telemetry"
    if module == "MatrixFactoryNetwork.fms.app[2].sink":
        return "dds"
    if AMR_ORDER_SINK_RE.match(module):
        return "orders"
    return None


def audit_single_run_conservation(path: Path, meta: Dict[str, object], tol_ms: float = 1e-9) -> Dict[str, object]:
    """Validate coordinator/sink conservation, domain-delay arithmetic, wired-only delay, and MAC invariants."""
    parsed = parse_sca_full(path)
    scalars: Dict[Tuple[str, str], float] = parsed["scalars"]  # type: ignore[assignment]
    stats: Dict[Tuple[str, str], Dict[str, float]] = parsed["stats"]  # type: ignore[assignment]

    cell = int(meta["cell"])
    namr = int(meta["nAmr"])
    coord = "MatrixFactoryNetwork.experimentCoordinator"
    errors: List[str] = []

    coord_delivered: Dict[str, int] = {}
    coord_retry_drops: Dict[str, int] = {}
    for cls in CLASSES:
        req_names = [
            f"n_generated_total_{cls}",
            f"n_generated_valid_{cls}",
            f"n_filtered_warmup_{cls}",
            f"n_filtered_horizon_{cls}",
            f"n_delivered_valid_{cls}",
            f"n_drop_queue_{cls}",
            f"n_drop_retry_{cls}",
            f"n_drop_other_{cls}",
            f"n_late_termination_{cls}",
        ]
        missing = [name for name in req_names if (coord, name) not in scalars]
        if missing:
            errors.append(f"missing coordinator scalars for {cls}: {missing[:3]}")
            continue
        vals = {name: scalars[(coord, name)] for name in req_names}
        for k, v in vals.items():
            if not math.isfinite(v) or abs(v - round(v)) > 1e-9:
                errors.append(f"non-integer coordinator count {k}={v}")
        iv = {k: int(round(v)) for k, v in vals.items()}
        lhs_total = iv[f"n_generated_valid_{cls}"] + iv[f"n_filtered_warmup_{cls}"] + iv[f"n_filtered_horizon_{cls}"]
        if iv[f"n_generated_total_{cls}"] != lhs_total:
            errors.append(f"{cls} total mismatch: {iv[f'n_generated_total_{cls}']} != {lhs_total}")
        lhs_valid = (
            iv[f"n_delivered_valid_{cls}"]
            + iv[f"n_drop_queue_{cls}"]
            + iv[f"n_drop_retry_{cls}"]
            + iv[f"n_drop_other_{cls}"]
            + iv[f"n_late_termination_{cls}"]
        )
        if iv[f"n_generated_valid_{cls}"] != lhs_valid:
            errors.append(f"{cls} valid conservation failed: {iv[f'n_generated_valid_{cls}']} != {lhs_valid}")
        coord_delivered[cls] = iv[f"n_delivered_valid_{cls}"]
        coord_retry_drops[cls] = iv[f"n_drop_retry_{cls}"]

    sink_modules_by_cls: Dict[str, Set[str]] = defaultdict(set)
    for mod, _name in scalars.keys():
        cls = _sink_class(mod)
        if cls is not None:
            sink_modules_by_cls[cls].add(mod)

    if len(sink_modules_by_cls.get("orders", set())) != namr:
        errors.append(f"expected {namr} order sinks, found {len(sink_modules_by_cls.get('orders', set()))}")
    for wired_cls in ("state", "telemetry", "dds"):
        if len(sink_modules_by_cls.get(wired_cls, set())) != 1:
            errors.append(f"expected 1 sink for {wired_cls}, found {len(sink_modules_by_cls.get(wired_cls, set()))}")

    sink_delivered_sum: Dict[str, int] = defaultdict(int)
    for cls, modules in sink_modules_by_cls.items():
        for mod in sorted(modules):
            s_req = ("n_received_total", "n_valid_delivered", "n_filtered_warmup", "n_filtered_horizon")
            if any((mod, n) not in scalars for n in s_req):
                errors.append(f"missing conservation scalars on sink {mod}")
                continue
            n_rx = int(round(scalars[(mod, "n_received_total")]))
            n_val = int(round(scalars[(mod, "n_valid_delivered")]))
            n_wu = int(round(scalars[(mod, "n_filtered_warmup")]))
            n_hz = int(round(scalars[(mod, "n_filtered_horizon")]))
            if n_rx != n_val + n_wu + n_hz:
                errors.append(f"sink {mod} rx conservation failed: {n_rx} != {n_val + n_wu + n_hz}")
            sink_delivered_sum[cls] += n_val

            e2e = stats.get((mod, "e2eDelay_ms"), {})
            wless = stats.get((mod, "wirelessDomainDelay_ms"), {})
            wsw = stats.get((mod, "wiredSwitchDelay_ms"), {})
            wser = stats.get((mod, "wireSerializationAndPropDelay_ms"), {})
            if not e2e or not wless or not wsw or not wser:
                errors.append(f"missing domain-delay statistic block on {mod}")
                continue
            cnt = int(round(e2e.get("count", -1.0)))
            if cnt != n_val:
                errors.append(f"sink {mod} e2eDelay_ms count={cnt} != n_valid_delivered={n_val}")
            if (
                int(round(wless.get("count", -1))) != cnt
                or int(round(wsw.get("count", -1))) != cnt
                or int(round(wser.get("count", -1))) != cnt
            ):
                errors.append(f"sink {mod} domain count mismatch across domain delay statistics")
            elif cnt > 0:
                diff = abs(e2e["mean"] - (wless["mean"] + wsw["mean"] + wser["mean"]))
                if not math.isfinite(diff) or diff > tol_ms:
                    errors.append(f"sink {mod} domain mean decomposition diff={diff}ms > tol={tol_ms}ms")
                if cls in ("telemetry", "dds") and abs(wless["mean"]) > tol_ms:
                    errors.append(f"wired-only flow {mod} ({cls}) has nonzero wirelessDomainDelay_ms={wless['mean']}")

    for cls in CLASSES:
        if cls in coord_delivered and sink_delivered_sum[cls] != coord_delivered[cls]:
            errors.append(f"{cls} sink vs coordinator delivered mismatch: {sink_delivered_sum[cls]} != {coord_delivered[cls]}")

    retry_vals = [v for (_m, k), v in scalars.items() if k == "packetSentToPeerWithRetry:count"]
    retry_limit_vals = [v for (_m, k), v in scalars.items() if k == "retryLimitReached:count"]
    sched_grants = [v for (_m, k), v in scalars.items() if k == "scheduledDcf_numGrantedInSlot"]
    if not retry_vals:
        errors.append("missing packetSentToPeerWithRetry:count MAC counters")
    total_retries = int(round(sum(retry_vals)))

    if cell in SCHED_CELLS:
        if total_retries != 0:
            errors.append(f"Scheduled Cell {cell} has nonzero MAC retries: {total_retries}")
        if sum(retry_limit_vals) != 0 or any(v != 0 for v in coord_retry_drops.values()):
            errors.append(f"Scheduled Cell {cell} has nonzero retryLimitReached/n_drop_retry")
        if sum(sched_grants) <= 0:
            errors.append(f"Scheduled Cell {cell} has no positive scheduledDcf_numGrantedInSlot")
    elif cell in CSMA_CELLS:
        if sched_grants:
            errors.append(f"CSMA Cell {cell} unexpectedly recorded scheduledDcf_numGrantedInSlot")

    return {
        "file": path.name,
        "cell": cell,
        "nAmr": namr,
        "phy": int(meta["phy"]),
        "telInterval": str(meta["telInterval"]),
        "rep": int(meta["rep"]),
        "total_retries": total_retries,
        "errors": errors,
    }


def _verify_manifest_cross_check(
    manifest_path: Path,
    sca_dir: Path,
    parsed_metas: List[Dict[str, object]],
    stage_namrs: Set[int],
) -> None:
    manifest_map: Dict[Tuple[int, int, int, str, int], Dict[str, str]] = {}
    with open(manifest_path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["exit_code"]) != 0:
                continue
            namr = int(row["nAmr"])
            if namr not in stage_namrs:
                continue
            key = (int(row["cell"]), namr, int(row["phy"]), str(row["telInterval"]), int(row["rep"]))
            manifest_map[key] = row

    sca_keys = {tuple(m["key"]) for m in parsed_metas}  # type: ignore[arg-type]
    missing_on_disk = sorted(set(manifest_map.keys()) - sca_keys)
    missing_in_manifest = sorted(sca_keys - set(manifest_map.keys()))
    if missing_on_disk:
        raise RuntimeError(f"Manifest has {len(missing_on_disk)} completed runs missing on disk: {missing_on_disk[:3]}")
    if missing_in_manifest:
        raise RuntimeError(f"Disk has {len(missing_in_manifest)} .sca(.gz) runs absent from manifest: {missing_in_manifest[:3]}")


def write_snapshot_sha256(
    out_path: Path,
    sca_dir: Path,
    *,
    manifest_path: Optional[Path] = None,
    root_dir: Optional[Path] = None,
) -> int:
    """Write sorted SHA-256 digests of manifest (if provided) and all .sca(.gz) files to out_path."""
    files: List[Path] = sorted([*sca_dir.glob("*.sca"), *sca_dir.glob("*.sca.gz")])
    if not files:
        raise FileNotFoundError(f"No .sca(.gz) files in {sca_dir}")
    if manifest_path is not None:
        files = [manifest_path] + files

    base = (root_dir or Path.cwd()).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp_path, "wt", encoding="utf-8") as out_f:
        for p in files:
            h = hashlib.sha256()
            with open(p, "rb") as src_f:
                while True:
                    chunk = src_f.read(1 << 20)
                    if not chunk:
                        break
                    h.update(chunk)
            resolved = p.resolve()
            try:
                disp = resolved.relative_to(base).as_posix()
            except ValueError:
                disp = str(p)
            out_f.write(f"{h.hexdigest()}  {disp}\n")
    tmp_path.replace(out_path)
    return len(files)


def audit_campaign(
    sca_dir: Path,
    *,
    manifest_path: Optional[Path] = None,
    expected_reps: int = 22,
    stage_namrs: Optional[Sequence[int]] = None,
    allow_partial_grid: bool = False,
    sample_frac: float = 0.05,
    seed: int = 20261114,
    tol_ms: float = 1e-9,
    snapshot_sha256: Optional[Path] = None,
) -> Dict[str, object]:
    """Run Phase 6a completeness + 6c independent conservation audit on sca_dir."""
    sca_dir = Path(sca_dir)
    sca_files = sorted([*sca_dir.glob("*.sca"), *sca_dir.glob("*.sca.gz")])
    if not sca_files:
        raise FileNotFoundError(f"No .sca or .sca.gz files found in {sca_dir}")

    allowed_namrs = set(stage_namrs) if stage_namrs is not None else set(ALL_NAMRS)
    metas: List[Dict[str, object]] = []
    seen_keys: Dict[Tuple[int, int, int, str, int], Path] = {}
    slice_reps: Dict[Tuple[int, int, int, str], Set[int]] = defaultdict(set)

    for p in sca_files:
        meta = parse_sca_header(p)
        namr = int(meta["nAmr"])
        if stage_namrs is not None and namr not in allowed_namrs:
            continue
        key = tuple(meta["key"])  # type: ignore[arg-type]
        if key in seen_keys:
            raise RuntimeError(f"Duplicate run key {key}: {seen_keys[key].name} and {p.name}")
        seen_keys[key] = p  # type: ignore[assignment]
        metas.append(meta)
        slice_reps[(int(meta["cell"]), namr, int(meta["phy"]), str(meta["telInterval"]))].add(int(meta["rep"]))

    if not metas:
        raise RuntimeError(f"No runs matching stage_namrs={sorted(allowed_namrs)} found in {sca_dir}")

    if manifest_path is not None:
        _verify_manifest_cross_check(Path(manifest_path), sca_dir, metas, allowed_namrs)

    # Check completeness & equal cell counts across every present (nAmr, phy, tel)
    present_slices = {(n, p, t) for (_c, n, p, t) in slice_reps.keys()}
    if not allow_partial_grid:
        expected_slices = {(n, p, t) for n in sorted(allowed_namrs) for p in ALL_PHYS for t in ALL_TELS}
        missing_slices = sorted(expected_slices - present_slices)
        if missing_slices:
            raise RuntimeError(f"Missing {len(missing_slices)} (nAmr, phy, tel) slices: {missing_slices[:5]}")

    rep_counts_by_slice: Dict[Tuple[int, int, str], int] = {}
    for namr, phy, tel in sorted(present_slices):
        per_cell_counts: List[int] = []
        for cell in ALL_CELLS:
            reps = sorted(slice_reps.get((cell, namr, phy, tel), set()))
            if not reps:
                raise RuntimeError(f"Missing Cell {cell} for slice (nAmr={namr}, phy={phy}, tel={tel})")
            if reps != list(range(len(reps))):
                raise RuntimeError(f"Non-contiguous replications in Cell {cell} {(namr, phy, tel)}: {reps[:10]}")
            if len(reps) < expected_reps:
                raise RuntimeError(
                    f"Under-replicated Cell {cell} {(namr, phy, tel)}: got {len(reps)} < expected {expected_reps}"
                )
            per_cell_counts.append(len(reps))
        if len(set(per_cell_counts)) != 1:
            raise RuntimeError(f"Unequal replication counts across cells for {(namr, phy, tel)}: {per_cell_counts}")
        rep_counts_by_slice[(namr, phy, tel)] = per_cell_counts[0]

    # Select corner runs + seeded random sample for full 6c conservation/domain audit
    present_namrs = sorted({int(m["nAmr"]) for m in metas})
    corner_namrs = {present_namrs[0], present_namrs[-1]}
    present_tels = sorted({str(m["telInterval"]) for m in metas}, key=lambda s: int(s[:-2]))
    corner_tels = {present_tels[0], present_tels[-1]}

    corner_metas: List[Dict[str, object]] = []
    other_metas: List[Dict[str, object]] = []
    for m in metas:
        if int(m["nAmr"]) in corner_namrs and str(m["telInterval"]) in corner_tels:
            corner_metas.append(m)
        else:
            other_metas.append(m)

    sample_n = 0
    if sample_frac > 0.0 and other_metas:
        sample_n = max(1, min(len(other_metas), int(math.ceil(len(other_metas) * sample_frac))))
        rng = random.Random(seed)
        sampled_others = rng.sample(other_metas, sample_n)
    else:
        sampled_others = []

    audited_metas = corner_metas + sampled_others
    run_failures: List[str] = []
    csma_300us_retries = 0
    saw_csma_300us = False

    for m in audited_metas:
        res = audit_single_run_conservation(Path(m["path"]), m, tol_ms=tol_ms)  # type: ignore[arg-type]
        if res["errors"]:
            run_failures.append(f"{res['file']}: {res['errors'][:3]}")
        if int(m["cell"]) in CSMA_CELLS and str(m["telInterval"]) == "300us":
            saw_csma_300us = True
            csma_300us_retries += int(res["total_retries"])

    if saw_csma_300us and csma_300us_retries <= 0:
        run_failures.append("CSMA 300us corner runs recorded 0 total MAC retries")

    if run_failures:
        raise RuntimeError(f"Phase 6c conservation/domain audit failed on {len(run_failures)} runs: {run_failures[:5]}")

    n_digested = 0
    if snapshot_sha256 is not None:
        n_digested = write_snapshot_sha256(snapshot_sha256, sca_dir, manifest_path=manifest_path)

    return {
        "sca_dir": str(sca_dir),
        "total_runs": len(metas),
        "n_slices": len(present_slices),
        "min_reps_per_cell": min(rep_counts_by_slice.values()),
        "max_reps_per_cell": max(rep_counts_by_slice.values()),
        "audited_runs": len(audited_metas),
        "corner_runs": len(corner_metas),
        "sampled_non_corner_runs": len(sampled_others),
        "csma_300us_total_retries": csma_300us_retries,
        "snapshot_digests_written": n_digested,
        "passed": True,
    }


def _parse_namrs(raw: Optional[str]) -> Optional[List[int]]:
    if not raw:
        return None
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def main(argv: Optional[Sequence[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sca-dir", type=Path, required=True, help="directory containing .sca(.gz) files")
    p.add_argument("--manifest", type=Path, default=None, help="optional manifest.csv for cross-check")
    p.add_argument("--expected-reps", type=int, default=22, help="minimum contiguous replications per cell/slice")
    p.add_argument("--stage-namrs", type=str, default=None, help="comma-separated nAmr values to scope (e.g. 40,80)")
    p.add_argument("--allow-partial-grid", action="store_true", help="allow subset of (nAmr, phy, telInterval) grid")
    p.add_argument("--sample-frac", type=float, default=0.05, help="fraction of non-corner runs to parse deeply")
    p.add_argument("--seed", type=int, default=20261114, help="PRNG seed for sampled audit runs")
    p.add_argument("--tol-ms", type=float, default=1e-9, help="domain-delay decomposition tolerance in ms")
    p.add_argument("--snapshot-sha256", type=Path, default=None, help="optional output path for stage SHA-256 snapshot")
    p.add_argument("--out-json", type=Path, default=None, help="optional output path for JSON audit summary")
    args = p.parse_args(argv)

    report = audit_campaign(
        args.sca_dir,
        manifest_path=args.manifest,
        expected_reps=args.expected_reps,
        stage_namrs=_parse_namrs(args.stage_namrs),
        allow_partial_grid=args.allow_partial_grid,
        sample_frac=args.sample_frac,
        seed=args.seed,
        tol_ms=args.tol_ms,
        snapshot_sha256=args.snapshot_sha256,
    )
    print(
        f"[PASS] Phase 6 audit: {report['total_runs']} runs across {report['n_slices']} slices "
        f"(reps/cell {report['min_reps_per_cell']}..{report['max_reps_per_cell']}); "
        f"deep-checked {report['audited_runs']} runs "
        f"({report['corner_runs']} corner + {report['sampled_non_corner_runs']} sampled, "
        f"CSMA 300us retries={report['csma_300us_total_retries']})"
    )
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
