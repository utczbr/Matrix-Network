#!/usr/bin/env python3
"""Equivalence and performance gate verifier for Tier A (INI config) + Tier B (jemalloc).

Verifies bit-identity between baseline and optimized OMNeT++ scalar outputs:
1. Per-file raw `.sca` / `.sca.gz` comparison:
   - Every ExperimentCoordinator scalar (`*.experimentCoordinator`).
   - Every DeadlineSink scalar (`*.sink` modules carrying `n_received_total`).
   - Every ScheduledDcf scalar (`scheduledDcf_*`).
   - Every whitelisted `@statistic` `:count` scalar (`packets:count` on `.app[*].source`,
     `packetSentToPeer:count`, `packetSentToPeerWithRetry:count`, `retryLimitReached:count`,
     and `frameSequenceDuration:count` on `.wlan[*].mac.dcf`).
   - Every scalar present in the optimized `.sca` file against the baseline `.sca` file.
   - Every DeadlineSink `statistic` block (`e2eDelay_ms`, `wirelessDomainDelay_ms`,
     `wiredSwitchDelay_ms`, `wireSerializationAndPropDelay_ms`, `stalenessTicks_10ms`,
     `stalenessTicks_50ms`, `stalenessTicks_500ms`) across `count`, `mean`, `stddev`,
     `min`, `max`, `sum`, and `sqrsum`.
2. Directory-level exported table comparison:
   - `lookup_summary`, `lookup_ecdf`, `lookup_replications` (`export_lookup.build_tables_from_sca`).
   - `lookup_domain_delay` (`export_lookup.build_domain_delay_table`).
   - `bottleneck_migration` (`bottleneck_migration.build_contrasts`).
3. Manifest performance & memory comparison:
   - Paired per-run `wall_seconds` speedup and `max_rss_kb` comparison across `(cell, nAmr, phy, telInterval, rep)`.
   - Grid-weighted 10,560-run campaign CPU-hour and 4-worker wall-day projection from the 192-run gate.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bottleneck_migration as bm  # noqa: E402
import export_lookup as ex  # noqa: E402

ALL_STAT_FIELDS = ("count", "mean", "stddev", "min", "max", "sum", "sqrsum")
WHITELISTED_STAT_SCALARS = (
    "packets:count",
    "packetSentToPeer:count",
    "packetSentToPeerWithRetry:count",
    "retryLimitReached:count",
)
DEADLINE_SINK_STAT_NAMES = (
    "e2eDelay_ms",
    "wirelessDomainDelay_ms",
    "wiredSwitchDelay_ms",
    "wireSerializationAndPropDelay_ms",
    "stalenessTicks_10ms",
    "stalenessTicks_50ms",
    "stalenessTicks_500ms",
)


def parse_sca_all_stat_fields(sca_path: Path) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Parse ``statistic`` blocks into ``(module, name) -> {count, mean, stddev, min, max, sum, sqrsum}``."""
    stats: Dict[Tuple[str, str], Dict[str, float]] = {}
    current: Optional[Dict[str, float]] = None
    opener = gzip.open if str(sca_path).endswith(".gz") else open
    with opener(sca_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("statistic "):
                parts = line.split()
                if len(parts) < 3:
                    raise RuntimeError(f"{Path(sca_path).name}: malformed statistic line {line!r}")
                current = stats.setdefault((parts[1], parts[2].strip('"')), {})
            elif current is not None and line.startswith("field "):
                parts = line.split()
                if len(parts) == 3 and parts[1] in ALL_STAT_FIELDS:
                    current[parts[1]] = float(parts[2])
            elif current is not None and line.startswith(("bin", "attr ")):
                continue
            else:
                current = None
    return stats


def _values_equal(a: float, b: float, tol: float = 0.0) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= tol


def is_required_scalar(
    mod: str,
    name: str,
    deadline_sink_mods: set[str],
    *,
    require_whitelisted_stats: bool = True,
) -> bool:
    """Return True if (mod, name) is a required production or verifier scalar."""
    if mod.endswith(".experimentCoordinator"):
        return ":" not in name
    if mod in deadline_sink_mods:
        # DeadlineSink's own finish() scalars are recordScalar() calls (no ':' mode suffix);
        # inherited PassivePacketSink @statistics (packets:count, packetLengths:sum, etc.) have ':'.
        return ":" not in name
    if name.startswith("scheduledDcf_"):
        return True
    if require_whitelisted_stats and name in WHITELISTED_STAT_SCALARS:
        if name == "packets:count" and ".app[" in mod and mod.endswith(".source"):
            return True
        if name == "retryLimitReached:count" and ".wlan[" in mod and mod.endswith(".mac.dcf.recoveryProcedure"):
            return True
        if name not in ("packets:count", "retryLimitReached:count") and ".wlan[" in mod and mod.endswith(".mac.dcf"):
            return True
    return False


def compare_sca_pair(
    base_path: Path,
    opt_path: Path,
    *,
    tol: float = 0.0,
    require_whitelisted_stats: bool = True,
) -> Dict[str, object]:
    """Compare one baseline .sca(.gz) against one optimized .sca(.gz) for exact equivalence."""
    base_path = Path(base_path)
    opt_path = Path(opt_path)
    if not base_path.exists():
        raise FileNotFoundError(f"Baseline scalar file not found: {base_path}")
    if not opt_path.exists():
        raise FileNotFoundError(f"Optimized scalar file not found: {opt_path}")

    base_attrs, base_scalars = ex.parse_sca_file(base_path)
    opt_attrs, opt_scalars = ex.parse_sca_file(opt_path)
    base_stats = parse_sca_all_stat_fields(base_path)
    opt_stats = parse_sca_all_stat_fields(opt_path)

    base_key = ex._run_key(base_attrs, base_path)
    opt_key = ex._run_key(opt_attrs, opt_path)
    if base_key != opt_key:
        raise RuntimeError(f"Run key mismatch between {base_path.name} ({base_key}) and {opt_path.name} ({opt_key})")

    base_sink_mods = {mod for (mod, sname) in base_scalars if sname == "n_received_total"}
    opt_sink_mods = {mod for (mod, sname) in opt_scalars if sname == "n_received_total"}
    if base_sink_mods != opt_sink_mods:
        raise RuntimeError(
            f"{opt_path.name}: DeadlineSink module set mismatch: base={len(base_sink_mods)}, opt={len(opt_sink_mods)}"
        )

    mismatches: List[str] = []

    # 1. Check that every required scalar in base exists in opt and matches
    required_checked = 0
    for (mod, name), bval in sorted(base_scalars.items()):
        if is_required_scalar(mod, name, base_sink_mods, require_whitelisted_stats=require_whitelisted_stats):
            required_checked += 1
            if (mod, name) not in opt_scalars:
                mismatches.append(f"MISSING required scalar {mod}.{name} in {opt_path.name} (base={bval})")
            else:
                oval = opt_scalars[(mod, name)]
                if not _values_equal(bval, oval, tol=tol):
                    mismatches.append(f"MISMATCH scalar {mod}.{name}: base={bval!r} != opt={oval!r}")

    # 2. Check that EVERY scalar present in opt also exists in base and matches
    opt_checked = 0
    for (mod, name), oval in sorted(opt_scalars.items()):
        opt_checked += 1
        if (mod, name) not in base_scalars:
            mismatches.append(f"EXTRA scalar {mod}.{name} in {opt_path.name} (opt={oval})")
        else:
            bval = base_scalars[(mod, name)]
            if not _values_equal(bval, oval, tol=tol):
                msg = f"MISMATCH scalar {mod}.{name}: base={bval!r} != opt={oval!r}"
                if msg not in mismatches:
                    mismatches.append(msg)

    # 3. Check all DeadlineSink statistic blocks (count, mean, stddev, min, max, sum, sqrsum)
    stat_fields_checked = 0
    for mod in sorted(base_sink_mods):
        for sname in DEADLINE_SINK_STAT_NAMES:
            if (mod, sname) not in base_stats:
                mismatches.append(f"MISSING statistic {mod}.{sname} in baseline {base_path.name}")
                continue
            if (mod, sname) not in opt_stats:
                mismatches.append(f"MISSING statistic {mod}.{sname} in optimized {opt_path.name}")
                continue
            bfields = base_stats[(mod, sname)]
            ofields = opt_stats[(mod, sname)]
            for fld in ALL_STAT_FIELDS:
                if fld in bfields or fld in ofields:
                    stat_fields_checked += 1
                    bval = bfields.get(fld, float("nan"))
                    oval = ofields.get(fld, float("nan"))
                    if not _values_equal(bval, oval, tol=tol):
                        mismatches.append(
                            f"MISMATCH statistic {mod}.{sname}.{fld}: base={bval!r} != opt={oval!r}"
                        )

    return {
        "base": str(base_path),
        "opt": str(opt_path),
        "run_key": base_key,
        "required_scalars_checked": required_checked,
        "opt_scalars_checked": opt_checked,
        "sink_stat_fields_checked": stat_fields_checked,
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }


def _assert_dataframes_equal(df_base: pd.DataFrame, df_opt: pd.DataFrame, name: str, tol: float = 0.0) -> None:
    if list(df_base.columns) != list(df_opt.columns):
        raise RuntimeError(f"{name}: column mismatch: base={list(df_base.columns)}, opt={list(df_opt.columns)}")
    if len(df_base) != len(df_opt):
        raise RuntimeError(f"{name}: row count mismatch: base={len(df_base)}, opt={len(df_opt)}")
    for col in df_base.columns:
        s_base = df_base[col]
        s_opt = df_opt[col]
        if pd.api.types.is_numeric_dtype(s_base):
            a = s_base.to_numpy(dtype=float)
            b = s_opt.to_numpy(dtype=float)
            both_nan = np.isnan(a) & np.isnan(b)
            diff = np.abs(a - b)
            bad = (~both_nan) & (np.isnan(a) | np.isnan(b) | (diff > tol))
            if np.any(bad):
                idx = int(np.flatnonzero(bad)[0])
                raise RuntimeError(
                    f"{name}: numeric mismatch in column {col!r} at row {idx}: "
                    f"base={a[idx]!r}, opt={b[idx]!r}"
                )
        else:
            neq = s_base.fillna("<NA>") != s_opt.fillna("<NA>")
            if neq.any():
                idx = int(np.flatnonzero(neq.to_numpy())[0])
                raise RuntimeError(
                    f"{name}: string mismatch in column {col!r} at row {idx}: "
                    f"base={s_base.iloc[idx]!r}, opt={s_opt.iloc[idx]!r}"
                )


def compare_sca_directories(
    base_dir: Path,
    opt_dir: Path,
    *,
    tol: float = 0.0,
    allow_subset: bool = False,
) -> Dict[str, object]:
    """Compare all .sca(.gz) files (and exported tables when directories cover identical run sets)."""
    base_dir = Path(base_dir)
    opt_dir = Path(opt_dir)
    base_files = sorted([*base_dir.glob("*.sca"), *base_dir.glob("*.sca.gz")])
    opt_files = sorted([*opt_dir.glob("*.sca"), *opt_dir.glob("*.sca.gz")])
    if not base_files:
        raise FileNotFoundError(f"No .sca files found in {base_dir}")
    if not opt_files:
        raise FileNotFoundError(f"No .sca files found in {opt_dir}")

    def _stem(p: Path) -> str:
        name = p.name
        if name.endswith(".sca.gz"):
            return name[: -len(".sca.gz")]
        if name.endswith(".sca"):
            return name[: -len(".sca")]
        return name

    base_map = {_stem(p): p for p in base_files}
    opt_map = {_stem(p): p for p in opt_files}
    if allow_subset:
        missing_in_base = sorted(set(opt_map.keys()) - set(base_map.keys()))
        if missing_in_base:
            raise RuntimeError(
                f"Subset mismatch: {len(missing_in_base)} file(s) in opt missing from base ({missing_in_base[:3]})"
            )
    elif set(base_map.keys()) != set(opt_map.keys()):
        missing = sorted(set(base_map.keys()) - set(opt_map.keys()))
        extra = sorted(set(opt_map.keys()) - set(base_map.keys()))
        raise RuntimeError(
            f"Directory file stem mismatch: {len(missing)} missing in opt ({missing[:3]}), "
            f"{len(extra)} extra in opt ({extra[:3]})"
        )

    total_req_scalars = 0
    total_opt_scalars = 0
    total_stat_fields = 0
    file_mismatches: Dict[str, List[str]] = {}

    stems_to_check = sorted(opt_map.keys())
    for stem in stems_to_check:
        res = compare_sca_pair(base_map[stem], opt_map[stem], tol=tol)
        total_req_scalars += int(res["required_scalars_checked"])
        total_opt_scalars += int(res["opt_scalars_checked"])
        total_stat_fields += int(res["sink_stat_fields_checked"])
        if not res["passed"]:
            file_mismatches[stem] = list(res["mismatches"])

    if file_mismatches:
        first_stem = next(iter(file_mismatches))
        raise RuntimeError(
            f"Raw .sca equivalence failed on {len(file_mismatches)}/{len(stems_to_check)} files; "
            f"first ({first_stem}): {file_mismatches[first_stem][:5]}"
        )

    summary_rows: Optional[int] = None
    ecdf_rows: Optional[int] = None
    replication_rows: Optional[int] = None
    domain_delay_rows: Optional[int] = None
    bottleneck_migration_rows: Optional[int] = None

    if set(base_map.keys()) == set(opt_map.keys()):
        # Compare exported tables across matched directories
        base_summary, base_ecdf = ex.build_tables_from_sca(base_dir, expected_reps=None, require_full_grid=False)
        opt_summary, opt_ecdf = ex.build_tables_from_sca(opt_dir, expected_reps=None, require_full_grid=False)
        base_reps = base_summary.attrs["replications"].sort_values(ex.KEY + ["rep"]).reset_index(drop=True)
        opt_reps = opt_summary.attrs["replications"].sort_values(ex.KEY + ["rep"]).reset_index(drop=True)

        _assert_dataframes_equal(base_summary, opt_summary, "lookup_summary", tol=tol)
        _assert_dataframes_equal(base_ecdf, opt_ecdf, "lookup_ecdf", tol=tol)
        _assert_dataframes_equal(base_reps, opt_reps, "lookup_replications", tol=tol)

        base_dom = ex.build_domain_delay_table(base_dir)
        opt_dom = ex.build_domain_delay_table(opt_dir)
        _assert_dataframes_equal(base_dom, opt_dom, "lookup_domain_delay", tol=tol)

        summary_rows = len(opt_summary)
        ecdf_rows = len(opt_ecdf)
        replication_rows = len(opt_reps)
        domain_delay_rows = len(opt_dom)

        if not allow_subset or set(int(c) for c in opt_reps["cell"].unique()) == {1, 2, 3, 4, 5, 6}:
            base_bm = bm.build_contrasts(base_reps)
            opt_bm = bm.build_contrasts(opt_reps)
            _assert_dataframes_equal(base_bm, opt_bm, "bottleneck_migration", tol=tol)
            bottleneck_migration_rows = len(opt_bm)

    return {
        "n_files": len(stems_to_check),
        "subset_mode": allow_subset,
        "total_required_scalars_checked": total_req_scalars,
        "total_opt_scalars_checked": total_opt_scalars,
        "total_sink_stat_fields_checked": total_stat_fields,
        "summary_rows": summary_rows,
        "ecdf_rows": ecdf_rows,
        "replication_rows": replication_rows,
        "domain_delay_rows": domain_delay_rows,
        "bottleneck_migration_rows": bottleneck_migration_rows,
        "passed": True,
    }


def compare_manifests(
    base_manifest: Path,
    opt_manifest: Path,
    *,
    allow_subset: bool = False,
) -> Dict[str, object]:
    """Compute paired per-run speedup, paired RSS differences, and 10,560-run projection from two manifests."""
    df_base = pd.read_csv(base_manifest)
    df_opt = pd.read_csv(opt_manifest)
    df_base = df_base[df_base["exit_code"] == 0].drop_duplicates(subset=["cell", "run_number"], keep="last")
    df_opt = df_opt[df_opt["exit_code"] == 0].drop_duplicates(subset=["cell", "run_number"], keep="last")

    key_cols = ["cell", "nAmr", "phy", "telInterval", "rep", "run_number"]
    merged = pd.merge(df_base, df_opt, on=key_cols, suffixes=("_base", "_opt"))
    if allow_subset:
        if len(merged) == 0 or len(merged) != len(df_opt):
            raise RuntimeError(
                f"Subset manifest pairing mismatch: base={len(df_base)}, opt={len(df_opt)}, paired={len(merged)}"
            )
    elif len(merged) != len(df_base) or len(merged) != len(df_opt):
        raise RuntimeError(
            f"Manifest pairing mismatch: base={len(df_base)}, opt={len(df_opt)}, paired={len(merged)}"
        )

    merged["speedup"] = merged["wall_seconds_base"] / merged["wall_seconds_opt"]
    merged["rss_mib_base"] = merged["max_rss_kb_base"] / 1024.0
    merged["rss_mib_opt"] = merged["max_rss_kb_opt"] / 1024.0
    merged["rss_diff_mib"] = merged["rss_mib_opt"] - merged["rss_mib_base"]
    merged["rss_ratio"] = merged["rss_mib_opt"] / merged["rss_mib_base"]
    merged["rss_pct_change"] = (merged["rss_ratio"] - 1.0) * 100.0
    merged["sca_kb_base"] = merged["sca_bytes_base"] / 1024.0
    merged["sca_kb_opt"] = merged["sca_bytes_opt"] / 1024.0

    total_base_s = float(merged["wall_seconds_base"].sum())
    total_opt_s = float(merged["wall_seconds_opt"].sum())
    overall_speedup = total_base_s / total_opt_s

    by_namr_phy = []
    for (namr, phy), grp in merged.groupby(["nAmr", "phy"], sort=True):
        b_mean = float(grp["wall_seconds_base"].mean())
        o_mean = float(grp["wall_seconds_opt"].mean())
        by_namr_phy.append({
            "nAmr": int(namr),
            "phy": int(phy),
            "n_runs": len(grp),
            "base_mean_s": round(b_mean, 2),
            "opt_mean_s": round(o_mean, 2),
            "speedup_ratio_of_means": round(b_mean / o_mean, 3),
            "speedup_mean_paired": round(float(grp["speedup"].mean()), 3),
            "speedup_min_paired": round(float(grp["speedup"].min()), 3),
            "speedup_max_paired": round(float(grp["speedup"].max()), 3),
            "base_mean_rss_mib": round(float(grp["rss_mib_base"].mean()), 2),
            "opt_mean_rss_mib": round(float(grp["rss_mib_opt"].mean()), 2),
            "paired_rss_diff_mib_mean": round(float(grp["rss_diff_mib"].mean()), 2),
            "paired_rss_pct_change_mean": round(float(grp["rss_pct_change"].mean()), 2),
            "base_max_rss_mib": round(float(grp["rss_mib_base"].max()), 2),
            "opt_max_rss_mib": round(float(grp["rss_mib_opt"].max()), 2),
        })

    by_cell = []
    for cell, grp in merged.groupby("cell", sort=True):
        b_mean = float(grp["wall_seconds_base"].mean())
        o_mean = float(grp["wall_seconds_opt"].mean())
        by_cell.append({
            "cell": int(cell),
            "n_runs": len(grp),
            "base_mean_s": round(b_mean, 2),
            "opt_mean_s": round(o_mean, 2),
            "speedup_ratio_of_means": round(b_mean / o_mean, 3),
            "base_mean_rss_mib": round(float(grp["rss_mib_base"].mean()), 2),
            "opt_mean_rss_mib": round(float(grp["rss_mib_opt"].mean()), 2),
            "paired_rss_diff_mib_mean": round(float(grp["rss_diff_mib"].mean()), 2),
            "opt_max_rss_mib": round(float(grp["rss_mib_opt"].max()), 2),
        })

    # Re-weight the full 10,560-run campaign across all 40 (N, lambda) grid slices
    # (N in {5, 10, 20, 40, 80}, 8 telIntervals in {2000..300us} -> lambda in {22.4..149.3 Mbps},
    # 264 runs per (N, lambda) slice = 6 cells * 2 PHYs * 22 reps = 10,560 runs total)
    # using PCHIP(N) x linear(lambda) between 2000us (22.4 Mbps) and 300us (149.3 Mbps).
    from scipy.interpolate import PchipInterpolator
    TEL_INTERVAL_TO_MBPS = ex.TEL_INTERVAL_TO_MBPS

    by_namr_tel = []
    for (namr, tel), grp in merged.groupby(["nAmr", "telInterval"], sort=True):
        b_mean = float(grp["wall_seconds_base"].mean())
        o_mean = float(grp["wall_seconds_opt"].mean())
        by_namr_tel.append({
            "nAmr": int(namr),
            "telInterval": str(tel),
            "n_runs": len(grp),
            "base_mean_s": round(b_mean, 2),
            "opt_mean_s": round(o_mean, 2),
            "speedup_ratio_of_means": round(b_mean / o_mean, 3),
            "base_mean_rss_mib": round(float(grp["rss_mib_base"].mean()), 2),
            "opt_mean_rss_mib": round(float(grp["rss_mib_opt"].mean()), 2),
            "paired_rss_diff_mib_mean": round(float(grp["rss_diff_mib"].mean()), 2),
            "paired_rss_pct_change_mean": round(float(grp["rss_pct_change"].mean()), 2),
            "base_max_rss_mib": round(float(grp["rss_mib_base"].max()), 2),
            "opt_max_rss_mib": round(float(grp["rss_mib_opt"].max()), 2),
        })

    ns_present = sorted(int(n) for n in merged["nAmr"].unique())
    tels_present = set(merged["telInterval"].unique())
    lams_8 = sorted(set(TEL_INTERVAL_TO_MBPS.values()))
    if ns_present == [5, 20, 40, 80] and {"2000us", "300us"}.issubset(tels_present):
        ns_obs = np.array([5, 20, 40, 80], dtype=float)
        b_2000 = merged[merged["telInterval"] == "2000us"].groupby("nAmr")["wall_seconds_base"].mean().reindex([5, 20, 40, 80]).to_numpy()
        b_300 = merged[merged["telInterval"] == "300us"].groupby("nAmr")["wall_seconds_base"].mean().reindex([5, 20, 40, 80]).to_numpy()
        o_2000 = merged[merged["telInterval"] == "2000us"].groupby("nAmr")["wall_seconds_opt"].mean().reindex([5, 20, 40, 80]).to_numpy()
        o_300 = merged[merged["telInterval"] == "300us"].groupby("nAmr")["wall_seconds_opt"].mean().reindex([5, 20, 40, 80]).to_numpy()
        b_lo_p = PchipInterpolator(ns_obs, b_2000)
        b_hi_p = PchipInterpolator(ns_obs, b_300)
        o_lo_p = PchipInterpolator(ns_obs, o_2000)
        o_hi_p = PchipInterpolator(ns_obs, o_300)
        proj_base_cpu_s = 0.0
        proj_opt_cpu_s = 0.0
        per_n_cpu_hours = {}
        for n in (5, 10, 20, 40, 80):
            wb0, wb1 = float(b_lo_p(n)), float(b_hi_p(n))
            wo0, wo1 = float(o_lo_p(n)), float(o_hi_p(n))
            nb_s = sum(264.0 * (wb0 + (wb1 - wb0) * (lam - 22.4) / (149.3 - 22.4)) for lam in lams_8)
            no_s = sum(264.0 * (wo0 + (wo1 - wo0) * (lam - 22.4) / (149.3 - 22.4)) for lam in lams_8)
            proj_base_cpu_s += nb_s
            proj_opt_cpu_s += no_s
            per_n_cpu_hours[str(n)] = {"base_cpu_h": round(nb_s / 3600.0, 1), "opt_cpu_h": round(no_s / 3600.0, 1)}
    else:
        mean_base_by_np = {
            (int(r["nAmr"]), int(r["phy"])): float(grp["wall_seconds_base"].mean())
            for (namr, phy), grp in merged.groupby(["nAmr", "phy"])
            for r in [{"nAmr": namr, "phy": phy}]
        }
        mean_opt_by_np = {
            (int(r["nAmr"]), int(r["phy"])): float(grp["wall_seconds_opt"].mean())
            for (namr, phy), grp in merged.groupby(["nAmr", "phy"])
            for r in [{"nAmr": namr, "phy": phy}]
        }
        for phy in (12, 54):
            if (10, phy) not in mean_opt_by_np and (5, phy) in mean_opt_by_np and (20, phy) in mean_opt_by_np:
                w = (10.0 - 5.0) / (20.0 - 5.0)
                mean_base_by_np[(10, phy)] = (1.0 - w) * mean_base_by_np[(5, phy)] + w * mean_base_by_np[(20, phy)]
                mean_opt_by_np[(10, phy)] = (1.0 - w) * mean_opt_by_np[(5, phy)] + w * mean_opt_by_np[(20, phy)]
        runs_per_np = 6 * 8 * 22
        proj_base_cpu_s = sum(mean_base_by_np[(n, p)] * runs_per_np for n in (5, 10, 20, 40, 80) for p in (12, 54) if (n, p) in mean_base_by_np)
        proj_opt_cpu_s = sum(mean_opt_by_np[(n, p)] * runs_per_np for n in (5, 10, 20, 40, 80) for p in (12, 54) if (n, p) in mean_opt_by_np)
        per_n_cpu_hours = {}

    opt_cpu_hours = round(proj_opt_cpu_s / 3600.0, 1)
    opt_wall_days_4w = round(proj_opt_cpu_s / (3600.0 * 24.0 * 4.0), 2)
    return {
        "n_paired_runs": len(merged),
        "total_base_wall_s": round(total_base_s, 2),
        "total_opt_wall_s": round(total_opt_s, 2),
        "base_mean_wall_s": round(total_base_s / len(merged), 2),
        "opt_mean_wall_s": round(total_opt_s / len(merged), 2),
        "overall_speedup_ratio_of_totals": round(overall_speedup, 3),
        "paired_speedup_mean": round(float(merged["speedup"].mean()), 3),
        "paired_speedup_median": round(float(merged["speedup"].median()), 3),
        "paired_speedup_min": round(float(merged["speedup"].min()), 3),
        "paired_speedup_max": round(float(merged["speedup"].max()), 3),
        "base_peak_rss_mib": round(float(merged["rss_mib_base"].max()), 2),
        "opt_peak_rss_mib": round(float(merged["rss_mib_opt"].max()), 2),
        "base_mean_rss_mib": round(float(merged["rss_mib_base"].mean()), 2),
        "opt_mean_rss_mib": round(float(merged["rss_mib_opt"].mean()), 2),
        "paired_rss_diff_mib_mean": round(float(merged["rss_diff_mib"].mean()), 2),
        "paired_rss_diff_mib_median": round(float(merged["rss_diff_mib"].median()), 2),
        "paired_rss_diff_mib_min": round(float(merged["rss_diff_mib"].min()), 2),
        "paired_rss_diff_mib_max": round(float(merged["rss_diff_mib"].max()), 2),
        "paired_rss_ratio_mean": round(float(merged["rss_ratio"].mean()), 3),
        "paired_rss_ratio_median": round(float(merged["rss_ratio"].median()), 3),
        "paired_rss_ratio_min": round(float(merged["rss_ratio"].min()), 3),
        "paired_rss_ratio_max": round(float(merged["rss_ratio"].max()), 3),
        "paired_rss_pct_change_mean": round(float(merged["rss_pct_change"].mean()), 2),
        "paired_rss_decreased_count": int((merged["rss_diff_mib"] < 0).sum()),
        "paired_rss_increased_count": int((merged["rss_diff_mib"] > 0).sum()),
        "base_mean_sca_kb": round(float(merged["sca_kb_base"].mean()), 2),
        "opt_mean_sca_kb": round(float(merged["sca_kb_opt"].mean()), 2),
        "by_namr_phy": by_namr_phy,
        "by_namr_tel": by_namr_tel,
        "by_cell": by_cell,
        "campaign_10560_projection": {
            "n_unique_loads": len(lams_8),
            "mean_load_mbps": round(float(np.mean(lams_8)), 2),
            "base_cpu_hours": round(proj_base_cpu_s / 3600.0, 1),
            "opt_cpu_hours": opt_cpu_hours,
            "base_wall_days_4workers": round(proj_base_cpu_s / (3600.0 * 24.0 * 4.0), 2),
            "opt_wall_days_4workers": opt_wall_days_4w,
            "planning_topup_margin_fraction": 0.10,
            "opt_cpu_hours_with_10pct_margin": round((proj_opt_cpu_s / 3600.0) * 1.10, 1),
            "opt_wall_days_4workers_with_10pct_margin": round((proj_opt_cpu_s * 1.10) / (3600.0 * 24.0 * 4.0), 2),
            "projected_campaign_speedup": round(proj_base_cpu_s / proj_opt_cpu_s, 3) if proj_opt_cpu_s > 0 else float("nan"),
            "per_n_cpu_hours": per_n_cpu_hours,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pair", action="append", default=[], metavar="BASE:OPT",
                   help="compare individual .sca(.gz) file pair BASE:OPT (may be repeated)")
    p.add_argument("--base-dir", type=Path, default=None,
                   help="baseline .sca(.gz) directory")
    p.add_argument("--opt-dir", type=Path, default=None,
                   help="optimized .sca(.gz) directory")
    p.add_argument("--base-manifest", type=Path, default=None,
                   help="baseline manifest.csv path")
    p.add_argument("--opt-manifest", type=Path, default=None,
                   help="optimized manifest.csv path")
    p.add_argument("--tol", type=float, default=0.0,
                   help="numeric comparison tolerance (default 0.0 for exact bit-identity)")
    p.add_argument("--allow-subset", action="store_true",
                   help="allow --opt-dir / --opt-manifest to be a non-empty subset of --base-dir / --base-manifest (for --no-jemalloc canary checks)")
    p.add_argument("--skip-whitelisted-stats", action="store_true",
                   help="do not require whitelisted @statistic :count scalars when comparing CLI-only test runs")
    p.add_argument("--out-json", type=Path, default=None,
                   help="optional path to write JSON summary report")
    args = p.parse_args(argv)

    if not args.pair and not (args.base_dir and args.opt_dir):
        p.error("Specify at least one --pair BASE:OPT or both --base-dir and --opt-dir")

    report: Dict[str, object] = {}

    if args.pair:
        pair_results = []
        for item in args.pair:
            if ":" not in item:
                raise ValueError(f"Invalid --pair {item!r}; expected BASE:OPT")
            b_str, o_str = item.split(":", 1)
            res = compare_sca_pair(
                Path(b_str),
                Path(o_str),
                tol=args.tol,
                require_whitelisted_stats=not args.skip_whitelisted_stats,
            )
            pair_results.append(res)
            status = "PASS" if res["passed"] else "FAIL"
            print(
                f"[{status}] {Path(b_str).name} vs {Path(o_str).name}: "
                f"req_scalars={res['required_scalars_checked']}, "
                f"opt_scalars={res['opt_scalars_checked']}, "
                f"stat_fields={res['sink_stat_fields_checked']}, "
                f"mismatches={len(res['mismatches'])}"
            )
            if not res["passed"]:
                for m in res["mismatches"][:10]:
                    print(f"  - {m}")
                raise SystemExit(1)
        report["pairs"] = pair_results

    if args.base_dir and args.opt_dir:
        dir_res = compare_sca_directories(args.base_dir, args.opt_dir, tol=args.tol, allow_subset=args.allow_subset)
        report["directory_equivalence"] = dir_res
        print(
            f"[PASS] Directory equivalence ({dir_res['n_files']} files, subset={dir_res['subset_mode']}): "
            f"req_scalars={dir_res['total_required_scalars_checked']}, "
            f"opt_scalars={dir_res['total_opt_scalars_checked']}, "
            f"stat_fields={dir_res['total_sink_stat_fields_checked']}, "
            f"summary={dir_res['summary_rows']}, ecdf={dir_res['ecdf_rows']}, "
            f"replications={dir_res['replication_rows']}, domain_delay={dir_res['domain_delay_rows']}, "
            f"bottleneck_migration={dir_res['bottleneck_migration_rows']}"
        )

    if args.base_manifest and args.opt_manifest:
        perf_res = compare_manifests(args.base_manifest, args.opt_manifest, allow_subset=args.allow_subset)
        report["manifest_comparison"] = perf_res
        proj = perf_res["campaign_10560_projection"]
        print(
            f"[PERF] Paired runs={perf_res['n_paired_runs']}: "
            f"mean wall {perf_res['base_mean_wall_s']}s -> {perf_res['opt_mean_wall_s']}s "
            f"(overall speedup={perf_res['overall_speedup_ratio_of_totals']}x, "
            f"paired mean={perf_res['paired_speedup_mean']}x, "
            f"min={perf_res['paired_speedup_min']}x, max={perf_res['paired_speedup_max']}x); "
            f"mean RSS {perf_res['base_mean_rss_mib']} -> {perf_res['opt_mean_rss_mib']} MiB "
            f"(paired mean diff {perf_res['paired_rss_diff_mib_mean']:+.2f} MiB, "
            f"{perf_res['paired_rss_pct_change_mean']:+.2f}%, "
            f"peak {perf_res['base_peak_rss_mib']} -> {perf_res['opt_peak_rss_mib']} MiB); "
            f"10,560-run projection: {proj['base_cpu_hours']} -> {proj['opt_cpu_hours']} CPU-h "
            f"({proj['base_wall_days_4workers']} -> {proj['opt_wall_days_4workers']} wall-days @ 4 workers; "
            f"+10% margin: {proj['opt_cpu_hours_with_10pct_margin']} CPU-h / {proj['opt_wall_days_4workers_with_10pct_margin']} d)"
        )

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

