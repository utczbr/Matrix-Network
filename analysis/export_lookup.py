"""Lookup-table export for the digital twin's NER engine (decisions.md section 5, Q3).

Supports TWO ingestion modes:
1. Stage 1 (--packets): Per-packet CSV table (used by the unit test suite and pilot debug runs).
2. Stage 2 (--sca-dir): Campaign-scale OMNeT++ .sca files produced by
   DeadlineSink and ExperimentCoordinator across Cell1_Sweep..Cell6_Sweep,
   enforcing the strict Packet Conservation Audit Gate.

Also provides ``interpolate`` (quantile-space monotone PCHIP along N_AMR and
lambda_tel, non-crossing guard, delays >= 0, saturation nearest-neighbour clamp,
no extrapolation with a logged warning; decisions.md section 5.4), the reference
inverse-transform sampler ``sample_delay`` / ``sample_flow_ner`` (SPEC-lookup-ner-integration.md
section 2.2), and the standalone G8a verification harness ``verify_g8a``.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import logging
import math
import re
import zlib
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# Avoid loading optional NumPy 1.x C-extensions (numexpr, bottleneck) when running under NumPy 2.x
sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

import deadline_metrics as dm

LOG = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0.0"
KEY = ["cell", "class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"]
PACKET_COLUMNS = KEY + ["rep", "g_s", "a_s", "drop_cause"]
HORIZON_LEAD_MS = max(dm.D_SPECTRUM_MS)      # common 100 ms horizon filter across all D
TAIL_N_P99 = 10**4
TAIL_N_P999 = 10**5

FIFO_CELLS = (1, 2)
TAS_CELLS = (5, 6)
FIFO_SATURATION_MBPS = 100.0       # decisions.md section 5.4 item 4
TAS_TELEMETRY_SATURATION_MBPS = 44.8

LOCKED_GRID_CELLS = (1, 2, 3, 4, 5, 6)
LOCKED_GRID_NAMRS = (5, 10, 20, 40, 80)
LOCKED_GRID_PHYS = (12, 54)
LOCKED_GRID_TELS = ("2000us", "996us", "747us", "600us", "527us", "472us", "407us", "300us")

# Map OMNeT++ telInterval parameter string -> aggregate payload Mbps across 4 stations
TEL_INTERVAL_TO_MBPS: Dict[str, float] = {
    "2000us": 22.4,
    "2ms": 22.4,
    "996us": 45.0,
    "747us": 60.0,
    "600us": 74.7,
    "527us": 85.0,
    "472us": 95.0,
    "407us": 110.0,
    "300us": 149.3,
}

SUMMARY_COLUMNS = (
    KEY
    + ["n_reps", "n_total", "p_loss", "n_Drop_Queue", "n_Drop_Retry", "n_Drop_Other", "n_Late_Termination"]
    + [f"miss_A_{d}ms" for d in dm.D_SPECTRUM_MS]
    + [f"miss_B_{d}ms" for d in dm.D_SPECTRUM_MS]
    + ["ci95_miss_B", "upper95_miss_B", "lat_p50", "lat_p90", "lat_p95", "lat_p99", "lat_p99_9",
       "flag_p99", "flag_p99_9", "schema_version"]
)
ECDF_COLUMNS = KEY + ["quantile_level", "delay_ms"]
REPLICATION_COLUMNS = KEY + ["rep", "n_total", "p_loss"] + [f"miss_B_{d}ms" for d in dm.D_SPECTRUM_MS]


# --------------------------------------------------------------------------- Stage 1 input (per-packet CSV)
def read_packets(path) -> pd.DataFrame:
    df = pd.read_csv(path, keep_default_na=True, na_values=["", "inf", "nan", "NaN"])
    missing = [c for c in PACKET_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"packet table is missing columns: {missing}")
    df["drop_cause"] = df["drop_cause"].fillna("").astype(str)
    return df[PACKET_COLUMNS]


# --------------------------------------------------------------------------- Stage 1 build tables
def build_tables(packets: pd.DataFrame, base_seed: int = 0,
                 warmup_s: float = dm.WARMUP_S, sim_limit_s: float = dm.SIM_LIMIT_S):
    """Return (lookup_summary, lookup_ecdf) DataFrames from a per-packet table."""
    summary_rows, ecdf_rows, replication_rows = [], [], []
    levels = np.array(dm.QUANTILE_LEVELS)
    idx = {lvl: i for i, lvl in enumerate(dm.QUANTILE_LEVELS)}

    for key, grp in packets.groupby(KEY, sort=True):
        cell, cls, n_amr, lam, phy = key
        if cls not in dm.NOMINAL_D_MS:
            raise ValueError(f"unknown traffic class {cls!r}")
        nominal = dm.NOMINAL_D_MS[cls]

        rates = {("A", d): [] for d in dm.D_SPECTRUM_MS} | {("B", d): [] for d in dm.D_SPECTRUM_MS}
        bins = {"n_valid": 0, "Drop_Queue": 0, "Drop_Retry": 0, "Drop_Other": 0, "Late_Termination": 0}
        nominal_misses = 0
        pooled = []

        reps = sorted(grp["rep"].unique())
        # Keep miss-rate estimates replication-level; pool only delivered delays for the ECDF.
        for rep in reps:
            rg = grp[grp["rep"] == rep]
            g = rg["g_s"].to_numpy(dtype=float)
            a = rg["a_s"].to_numpy(dtype=float)
            cause = rg["drop_cause"].to_numpy(dtype=object)

            phase = dm.replication_phase_ms(base_seed, rep)
            kw = dict(tick_ms=dm.T_PRIMARY_MS, phase_ms=phase,
                      warmup_s=warmup_s, sim_limit_s=sim_limit_s,
                      horizon_lead_ms=HORIZON_LEAD_MS)

            for d in dm.D_SPECTRUM_MS:
                rates[("A", d)].append(dm.miss_rate(g, a, d, definition="A", **kw))
                rates[("B", d)].append(dm.miss_rate(g, a, d, definition="B", **kw))

            oc = dm.outcome_counts(g, a, cause, nominal, definition="B", **kw)
            for k in bins:
                bins[k] += oc[k]
            nominal_misses += (
                oc["Late_Arrival"]
                + oc["Late_Termination"]
                + oc["Drop_Queue"]
                + oc["Drop_Retry"]
                + oc["Drop_Other"]
            )
            rep_drops = oc["Drop_Queue"] + oc["Drop_Retry"] + oc["Drop_Other"]
            rep_row = {
                **dict(zip(KEY, key)),
                "rep": int(rep),
                "n_total": oc["n_valid"],
                "p_loss": (rep_drops / oc["n_valid"]) if oc["n_valid"] else float("nan"),
            }
            for d in dm.D_SPECTRUM_MS:
                rep_row[f"miss_B_{d}ms"] = rates[("B", d)][-1]
            replication_rows.append(rep_row)

            keep = dm.valid_mask(g, HORIZON_LEAD_MS, dm.T_PRIMARY_MS, phase, warmup_s, sim_limit_s)
            dly = dm.delay_ms(g, a)
            pooled.append(dly[keep & np.isfinite(dly)])

        pooled = np.concatenate(pooled) if pooled else np.array([])
        n_total = bins["n_valid"]
        drops = bins["Drop_Queue"] + bins["Drop_Retry"] + bins["Drop_Other"]
        qs = np.quantile(pooled, levels) if pooled.size else np.full(levels.shape, np.nan)

        row = dict(zip(KEY, key))
        row.update(
            n_reps=len(reps),
            n_total=n_total,
            p_loss=(drops / n_total) if n_total else np.nan,
            n_Drop_Queue=bins["Drop_Queue"],
            n_Drop_Retry=bins["Drop_Retry"],
            n_Drop_Other=bins["Drop_Other"],
            n_Late_Termination=bins["Late_Termination"],
        )
        for d in dm.D_SPECTRUM_MS:
            row[f"miss_A_{d}ms"] = _nanmean(rates[("A", d)])
            row[f"miss_B_{d}ms"] = _nanmean(rates[("B", d)])

        row.update(
            ci95_miss_B=dm.student_t_halfwidth(rates[("B", nominal)]),
            upper95_miss_B=dm.wilson_upper(nominal_misses, n_total),
            lat_p50=qs[idx[0.50]],
            lat_p90=qs[idx[0.90]],
            lat_p95=qs[idx[0.95]],
            lat_p99=qs[idx[0.99]],
            lat_p99_9=qs[idx[0.999]],
            flag_p99="OK" if pooled.size >= TAIL_N_P99 else "INSUFFICIENT_TAIL_SAMPLES",
            flag_p99_9="OK" if pooled.size >= TAIL_N_P999 else "INSUFFICIENT_TAIL_SAMPLES",
            schema_version=SCHEMA_VERSION,
        )
        summary_rows.append(row)

        if pooled.size:
            for lvl, dly in zip(dm.QUANTILE_LEVELS, qs):
                ecdf_rows.append({**dict(zip(KEY, key)), "quantile_level": lvl, "delay_ms": float(dly)})

    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    ecdf = pd.DataFrame(ecdf_rows, columns=ECDF_COLUMNS)
    summary.attrs["replications"] = pd.DataFrame(replication_rows, columns=REPLICATION_COLUMNS)
    return summary, ecdf


# --------------------------------------------------------------------------- Stage 2 input (.sca campaign files)
def parse_sca_file(sca_path: Path) -> Tuple[Dict[str, str], Dict[Tuple[str, str], float]]:
    """Parse itervar/param headers and scalar (module, name) -> value from an OMNeT++ .sca file."""
    attrs: Dict[str, str] = {}
    scalars: Dict[Tuple[str, str], float] = {}
    opener = gzip.open if str(sca_path).endswith(".gz") else open
    with opener(sca_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(("attr ", "itervar ", "param ")):
                parts = line.split(None, 2)
                if len(parts) == 3:
                    k, v = parts[1], parts[2].strip('"')
                    attrs[k] = v
            elif line.startswith("scalar "):
                # Format: scalar <module> <name> <value>
                m = re.match(r'^scalar\s+(\S+)\s+(?:"([^"]+)"|(\S+))\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|nan|inf|-inf)$', line)
                if m:
                    mod = m.group(1)
                    sname = m.group(2) if m.group(2) is not None else m.group(3)
                    val = float(m.group(4))
                    scalars[(mod, sname)] = val
    return attrs, scalars


def check_repetition_floor(df_runs: pd.DataFrame, expected_reps: Optional[int]) -> None:
    """Contiguous-floor repetition gate (replaces the exact ``reps == range(R)`` equality).

    Every key must carry seeds ``0..k-1`` with no gaps and ``k >= expected_reps``, and all six
    cells of an (class, N, lambda, PHY) slice must share the same ``k`` so the six-cell pairing
    used by ``bottleneck_migration.py`` stays balanced after a slice top-up. Duplicates are
    rejected separately by the caller.
    """
    if expected_reps is None:
        return
    k_by_key = {}
    for key, grp in df_runs.groupby(KEY, sort=True):
        reps = sorted({int(value) for value in grp["rep"]})
        k = len(reps)
        if reps != list(range(k)):
            raise RuntimeError(f"{key}: repetitions must be contiguous from 0 with no gaps, found {reps}")
        if k < expected_reps:
            raise RuntimeError(
                f"{key}: expected repetitions 0..{expected_reps - 1} at least, found only {k}")
        k_by_key[key] = k
    slices = {}
    for (cell, cls, n_amr, lam, phy), k in k_by_key.items():
        slices.setdefault((cls, n_amr, lam, phy), {})[cell] = k
    for slice_key, by_cell in sorted(slices.items()):
        if len(set(by_cell.values())) != 1:
            raise RuntimeError(
                f"slice {slice_key}: cells have unequal repetition counts {dict(sorted(by_cell.items()))}")


# --------------------------------------------------------------------------- domain-delay statistics
# DeadlineSink records these as OMNeT++ ``statistic`` blocks (count, mean, ..., histogram bins), not
# scalars, so the scalar parser never sees them. Read count and mean only; bins are ignored, so the
# result is identical whether bin recording is on or off.
DOMAIN_STATS = {
    "wireless": "wirelessDomainDelay_ms",
    "wired_switch": "wiredSwitchDelay_ms",
    "wire_serialization": "wireSerializationAndPropDelay_ms",
}
E2E_STAT = "e2eDelay_ms"
_STAT_FIELDS = ("count", "mean", "stddev")


def parse_sca_statistics(sca_path: Path) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Parse ``statistic`` blocks into ``(module, name) -> {count, mean, stddev}``; bins are ignored."""
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
                if len(parts) == 3 and parts[1] in _STAT_FIELDS:
                    current[parts[1]] = float(parts[2])
            elif current is not None and line.startswith(("bin", "attr ")):
                continue
            else:
                current = None
    return stats


def weighted_mean(parts: Sequence[Tuple[float, float]]) -> float:
    """Count-weighted mean of ``(count, mean)`` pairs; empty sinks (count 0) are skipped."""
    total = sum(count for count, _ in parts)
    if total <= 0:
        return float("nan")
    return sum(count * mean for count, mean in parts if count > 0) / total


def class_sink_modules(scalars: Dict[Tuple[str, str], float], cls: str) -> List[str]:
    """DeadlineSink modules of one traffic class in a run (Orders has one per AMR)."""
    return sorted(mod for (mod, sname) in scalars if sname == "n_valid_delivered" and (
        (cls == "orders" and ".amr[" in mod and ".app[1].sink" in mod) or
        (cls == "state" and mod.endswith(".fms.app[0].sink")) or
        (cls == "telemetry" and mod.endswith(".fms.app[1].sink")) or
        (cls == "dds" and mod.endswith(".fms.app[2].sink"))))


def _run_key(attrs: Dict[str, str], sca_path: Path):
    """(cell, N_AMR, lambda, PHY, repetition) of one run, as in ``build_tables_from_sca``."""
    cell_match = re.search(r"Cell(\d)", attrs.get("configname", ""))
    if not cell_match:
        return None
    tel_str = attrs.get("telInterval", "2000us").strip('"')
    if tel_str not in TEL_INTERVAL_TO_MBPS:
        raise RuntimeError(f"{sca_path.name}: unmapped telInterval {tel_str!r}")
    phy = int(float(attrs.get("phyRate", "54Mbps").replace("Mbps", "").strip('"')))
    return (int(cell_match.group(1)), int(attrs.get("nAmr", attrs.get("*.numAmrs", 10))),
            TEL_INTERVAL_TO_MBPS[tel_str], phy, int(attrs.get("repetition", 0)))


def build_domain_delay_table(sca_dir: Path, tolerance_ms: float = 1e-6) -> pd.DataFrame:
    """Per-run, per-class, per-domain delivered-packet delay means from ``statistic`` blocks.

    Columns: cell, class, N_AMR, lambda_tel_Mbps, phy_rate_Mbps, rep, domain, n_samples, mean_ms,
    e2e_mean_ms. Counts are pooled over a class's sinks (Orders has one per AMR) and means are
    count-weighted. Audits: every sink must carry every statistic; the statistic count must equal
    ``n_domain_breakdown_valid``; and the three domain means must sum to the end-to-end mean
    (checked whenever the end-to-end statistic covers the same population).
    """
    sca_files = sorted([*Path(sca_dir).glob("*.sca"), *Path(sca_dir).glob("*.sca.gz")])
    if not sca_files:
        raise FileNotFoundError(f"No .sca files found in {sca_dir}")
    records = []
    for sca_path in sca_files:
        attrs, scalars = parse_sca_file(sca_path)
        key = _run_key(attrs, sca_path)
        if key is None:
            continue
        cell, n_amr, lam, phy, rep = key
        stats = parse_sca_statistics(sca_path)
        for cls in ("orders", "dds", "state", "telemetry"):
            sink_mods = class_sink_modules(scalars, cls)
            if not sink_mods:
                raise RuntimeError(f"{sca_path.name}: no DeadlineSink found for class {cls}")
            n_domain = int(sum(scalars[(m, "n_domain_breakdown_valid")] for m in sink_mods))
            means, counts = {}, {}
            for domain, stat in DOMAIN_STATS.items():
                missing = [m for m in sink_mods if "count" not in stats.get((m, stat), {})
                           or "mean" not in stats.get((m, stat), {})]
                if missing:
                    raise RuntimeError(
                        f"{sca_path.name}: missing statistic {stat} on {len(missing)} {cls} sink(s), e.g. {missing[0]}")
                parts = [(stats[(m, stat)]["count"], stats[(m, stat)]["mean"]) for m in sink_mods]
                counts[domain] = int(sum(count for count, _ in parts))
                if counts[domain] != n_domain:
                    raise RuntimeError(
                        f"{sca_path.name} ({cls}): {stat} count {counts[domain]} != "
                        f"n_domain_breakdown_valid {n_domain}")
                means[domain] = weighted_mean(parts)
            e2e_mean = float("nan")
            e2e_parts = [(stats.get((m, E2E_STAT), {}).get("count"), stats.get((m, E2E_STAT), {}).get("mean"))
                         for m in sink_mods]
            if all(c is not None and mu is not None for c, mu in e2e_parts) \
                    and int(sum(c for c, _ in e2e_parts)) == n_domain:
                e2e_mean = weighted_mean(e2e_parts)
                if n_domain > 0 and abs(sum(means.values()) - e2e_mean) > tolerance_ms:
                    raise RuntimeError(
                        f"{sca_path.name} ({cls}): domain means sum to {sum(means.values()):.9f} ms "
                        f"but the end-to-end mean is {e2e_mean:.9f} ms")
            for domain in DOMAIN_STATS:
                records.append({"cell": cell, "class": cls, "N_AMR": n_amr, "lambda_tel_Mbps": lam,
                                "phy_rate_Mbps": phy, "rep": rep, "domain": domain,
                                "n_samples": counts[domain], "mean_ms": means[domain],
                                "e2e_mean_ms": e2e_mean})
    return pd.DataFrame(records).sort_values(
        ["cell", "class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps", "rep", "domain"]).reset_index(drop=True)


def build_tables_from_sca(sca_dir: Path, strict_conservation: bool = True,
                          expected_reps: Optional[int] = None,
                          require_full_grid: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Ingest production scalars and build ``(lookup_summary, lookup_ecdf)``.

    Stage 2 never substitutes zero for an absent counter. The coordinator owns
    generated/drop/termination accounting and pooled per-class quantiles; the
    sinks own delivered deadline misses. Both sides must agree exactly.
    """
    sca_files = sorted([*Path(sca_dir).glob("*.sca"), *Path(sca_dir).glob("*.sca.gz")])
    if not sca_files:
        raise FileNotFoundError(f"No .sca files found in {sca_dir}")

    records = []
    levels = list(dm.QUANTILE_LEVELS)

    for sca_path in sca_files:
        attrs, scalars = parse_sca_file(sca_path)
        configname = attrs.get("configname", "")
        cell_match = re.search(r"Cell(\d)", configname)
        if not cell_match:
            continue
        cell = int(cell_match.group(1))

        n_amr = int(attrs.get("nAmr", attrs.get("*.numAmrs", 10)))
        tel_str = attrs.get("telInterval", "2000us").strip('"')
        if tel_str not in TEL_INTERVAL_TO_MBPS:
            raise RuntimeError(f"{sca_path.name}: unmapped telInterval {tel_str!r}")
        lam = TEL_INTERVAL_TO_MBPS[tel_str]
        phy_str = attrs.get("phyRate", "54Mbps").replace("Mbps", "").strip('"')
        phy = int(float(phy_str))
        rep = int(attrs.get("repetition", 0))

        coordinator_mods = sorted({mod for mod, _ in scalars if mod.endswith(".experimentCoordinator")})
        if len(coordinator_mods) != 1:
            raise RuntimeError(f"{sca_path.name}: expected one ExperimentCoordinator, found {coordinator_mods}")
        coordinator = coordinator_mods[0]

        def required(module: str, name: str) -> float:
            try:
                return scalars[(module, name)]
            except KeyError as exc:
                raise RuntimeError(f"{sca_path.name}: missing scalar {module}.{name}") from exc

        # Aggregate DeadlineSink scalars per class (Orders has one sink per AMR).
        for cls in ("orders", "dds", "state", "telemetry"):
            sink_mods = [mod for (mod, sname) in scalars if sname == "n_valid_delivered" and (
                (cls == "orders" and ".amr[" in mod and ".app[1].sink" in mod) or
                (cls == "state" and mod.endswith(".fms.app[0].sink")) or
                (cls == "telemetry" and mod.endswith(".fms.app[1].sink")) or
                (cls == "dds" and mod.endswith(".fms.app[2].sink"))
            )]
            if not sink_mods:
                raise RuntimeError(f"{sca_path.name}: no DeadlineSink found for class {cls}")

            n_rx_total = int(sum(required(m, "n_received_total") for m in sink_mods))
            n_warmup = int(sum(required(m, "n_filtered_warmup") for m in sink_mods))
            n_horizon = int(sum(required(m, "n_filtered_horizon") for m in sink_mods))
            n_deliv = int(sum(required(m, "n_valid_delivered") for m in sink_mods))
            n_domain = int(sum(required(m, "n_domain_breakdown_valid") for m in sink_mods))
            n_generated = int(required(coordinator, f"n_generated_valid_{cls}"))
            n_coord_deliv = int(required(coordinator, f"n_delivered_valid_{cls}"))
            n_drop_queue = int(required(coordinator, f"n_drop_queue_{cls}"))
            n_drop_retry = int(required(coordinator, f"n_drop_retry_{cls}"))
            n_drop_other = int(required(coordinator, f"n_drop_other_{cls}"))
            n_late_termination = int(required(coordinator, f"n_late_termination_{cls}"))

            # Cross-check the coordinator ledger against sink-side receipt and domain counts.
            if strict_conservation:
                if n_rx_total != n_deliv + n_warmup + n_horizon:
                    raise RuntimeError(
                        f"Sink conservation failed in {sca_path.name} ({cls}): "
                        f"{n_rx_total} != {n_deliv}+{n_warmup}+{n_horizon}")
                if n_coord_deliv != n_deliv or n_domain != n_deliv:
                    raise RuntimeError(
                        f"Delivery/domain audit failed in {sca_path.name} ({cls}): "
                        f"coordinator={n_coord_deliv}, sink={n_deliv}, domain={n_domain}")
                terminal = n_deliv + n_drop_queue + n_drop_retry + n_drop_other + n_late_termination
                if n_generated != terminal:
                    raise RuntimeError(
                        f"Full conservation failed in {sca_path.name} ({cls}): generated={n_generated}, "
                        f"delivered={n_deliv}, queue={n_drop_queue}, retry={n_drop_retry}, "
                        f"other={n_drop_other}, termination={n_late_termination}")

                for tick in (10, 50, 500):
                    phase_name = f"tick_phase_offset_{tick}ms_sec"
                    phase = required(coordinator, phase_name)
                    sink_phases = [required(m, phase_name) for m in sink_mods]
                    if any(value != phase for value in sink_phases):
                        raise RuntimeError(f"{sca_path.name} ({cls}): tick phase {tick}ms is not replication-global")

            rec = {
                "cell": cell,
                "class": cls,
                "N_AMR": n_amr,
                "lambda_tel_Mbps": lam,
                "phy_rate_Mbps": phy,
                "rep": rep,
                "n_generated": n_generated,
                "n_deliv": n_deliv,
                "n_drop_queue": n_drop_queue,
                "n_drop_retry": n_drop_retry,
                "n_drop_other": n_drop_other,
                "n_late_termination": n_late_termination,
            }
            for d in dm.D_SPECTRUM_MS:
                rec[f"n_miss_A_{d}ms"] = int(sum(required(m, f"n_miss_A_{d}ms") for m in sink_mods))
                rec[f"n_miss_B_{d}ms"] = int(sum(required(m, f"n_miss_B_{d}ms") for m in sink_mods))

            for lvl in levels:
                q_key = f"ecdf_q_{lvl:.3f}"
                rec[q_key] = required(coordinator, f"ecdf_{cls}_q_{lvl:.3f}") if n_deliv else float("nan")

            records.append(rec)

    df_runs = pd.DataFrame(records)
    if df_runs.empty:
        raise RuntimeError(f"No Cell1..Cell6 campaign records found in {sca_dir}")
    duplicate = df_runs.duplicated(KEY + ["rep"], keep=False)
    if duplicate.any():
        raise RuntimeError(f"duplicate replication rows: {df_runs.loc[duplicate, KEY + ['rep']].to_dict('records')[:5]}")

    if require_full_grid:
        expected_keys = {
            (cell, cls, n, lam, phy)
            for cell in range(1, 7)
            for cls in dm.CLASSES
            for n in (5, 10, 20, 40, 80)
            for lam in sorted(set(TEL_INTERVAL_TO_MBPS.values()))
            for phy in (12, 54)
        }
        observed_keys = set(map(tuple, df_runs[KEY].itertuples(index=False, name=None)))
        missing = expected_keys - observed_keys
        extra = observed_keys - expected_keys
        if missing or extra:
            raise RuntimeError(f"campaign grid mismatch: {len(missing)} missing, {len(extra)} unexpected; sample={list(missing)[:3]}")

    check_repetition_floor(df_runs, expected_reps)

    summary_rows, ecdf_rows = [], []
    idx = {lvl: i for i, lvl in enumerate(levels)}

    for key, grp in df_runs.groupby(KEY, sort=True):
        cell, cls, n_amr, lam, phy = key
        nominal = dm.NOMINAL_D_MS[cls]
        reps = set(int(value) for value in grp["rep"])
        n_reps = len(reps)

        n_deliv_total = int(grp["n_deliv"].sum())
        n_drop_q = int(grp["n_drop_queue"].sum())
        n_drop_r = int(grp["n_drop_retry"].sum())
        n_drop_o = int(grp["n_drop_other"].sum())
        n_late_t = int(grp["n_late_termination"].sum())
        drops = n_drop_q + n_drop_r + n_drop_o
        n_total = int(grp["n_generated"].sum())

        # Weight per-run quantiles by valid deliveries when combining replications.
        def weighted_quantile_scalar(level: float) -> float:
            values = grp[f"ecdf_q_{level:.3f}"].to_numpy(dtype=float)
            weights = grp["n_deliv"].to_numpy(dtype=float)
            keep = np.isfinite(values) & (weights > 0)
            return float(np.average(values[keep], weights=weights[keep])) if keep.any() else float("nan")

        qs = [weighted_quantile_scalar(level) for level in levels]

        row = dict(zip(KEY, key))
        row.update(
            n_reps=n_reps,
            n_total=n_total,
            p_loss=(drops / n_total) if n_total else float("nan"),
            n_Drop_Queue=n_drop_q,
            n_Drop_Retry=n_drop_r,
            n_Drop_Other=n_drop_o,
            n_Late_Termination=n_late_t,
        )

        # Drops and unfinished packets are misses at every deadline, but only drops enter p_loss.
        rep_totals = grp["n_generated"]
        rep_terminal_misses = grp["n_drop_queue"] + grp["n_drop_retry"] + grp["n_drop_other"] + grp["n_late_termination"]

        for d in dm.D_SPECTRUM_MS:
            rates_a = ((grp[f"n_miss_A_{d}ms"] + rep_terminal_misses) / rep_totals).to_numpy(dtype=float)
            rates_b = ((grp[f"n_miss_B_{d}ms"] + rep_terminal_misses) / rep_totals).to_numpy(dtype=float)
            row[f"miss_A_{d}ms"] = _nanmean(rates_a)
            row[f"miss_B_{d}ms"] = _nanmean(rates_b)
            if d == nominal:
                nom_rates_b = rates_b

        row.update(
            ci95_miss_B=dm.student_t_halfwidth(nom_rates_b),
            upper95_miss_B=dm.wilson_upper(
                int(grp[f"n_miss_B_{nominal}ms"].sum() + rep_terminal_misses.sum()), n_total),
            lat_p50=qs[idx[0.50]],
            lat_p90=qs[idx[0.90]],
            lat_p95=qs[idx[0.95]],
            lat_p99=qs[idx[0.99]],
            lat_p99_9=qs[idx[0.999]],
            flag_p99="OK" if n_deliv_total >= TAIL_N_P99 else "INSUFFICIENT_TAIL_SAMPLES",
            flag_p99_9="OK" if n_deliv_total >= TAIL_N_P999 else "INSUFFICIENT_TAIL_SAMPLES",
            schema_version=SCHEMA_VERSION,
        )
        summary_rows.append(row)

        if n_deliv_total > 0:
            for lvl, dly in zip(levels, qs):
                ecdf_rows.append({**dict(zip(KEY, key)), "quantile_level": lvl, "delay_ms": float(dly)})

    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    ecdf = pd.DataFrame(ecdf_rows, columns=ECDF_COLUMNS)
    replication_rows = []
    for _, run in df_runs.iterrows():
        terminal_misses = run["n_drop_queue"] + run["n_drop_retry"] + run["n_drop_other"] + run["n_late_termination"]
        row = {column: run[column] for column in KEY + ["rep"]}
        row["n_total"] = int(run["n_generated"])
        row["p_loss"] = ((run["n_drop_queue"] + run["n_drop_retry"] + run["n_drop_other"])
                         / run["n_generated"] if run["n_generated"] else float("nan"))
        for deadline in dm.D_SPECTRUM_MS:
            row[f"miss_B_{deadline}ms"] = ((run[f"n_miss_B_{deadline}ms"] + terminal_misses)
                                             / run["n_generated"] if run["n_generated"] else float("nan"))
        replication_rows.append(row)
    summary.attrs["replications"] = pd.DataFrame(replication_rows, columns=REPLICATION_COLUMNS)
    return summary, ecdf


def _nanmean(values) -> float:
    x = np.asarray(values, dtype=float)
    return float(np.nanmean(x)) if np.isfinite(x).any() else float("nan")


# --------------------------------------------------------------------------- output
def write_tables(summary: pd.DataFrame, ecdf: pd.DataFrame, out_dir) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "lookup_summary.csv", index=False)
    ecdf.to_csv(out / "lookup_ecdf.csv", index=False)
    summary.to_json(out / "lookup_summary.json", orient="records", indent=2)
    ecdf.to_json(out / "lookup_ecdf.json", orient="records", indent=2)
    replications = summary.attrs.get("replications")
    if isinstance(replications, pd.DataFrame) and not replications.empty:
        selected = summary[KEY].drop_duplicates()
        replications = replications.merge(selected, on=KEY, how="inner")
        replications.to_csv(out / "lookup_replications.csv", index=False)


# --------------------------------------------------------------------------- interpolation (section 5.4)
def interpolate(summary: pd.DataFrame, ecdf: pd.DataFrame, *,
                cell: int, cls: str, phy_rate: int, n_amr: float, lam: float) -> Dict[str, object]:
    """Delay quantiles and p_loss at an arbitrary (N_AMR, lambda_tel) inside the grid."""
    sel_s = (summary["cell"] == cell) & (summary["class"] == cls) & (summary["phy_rate_Mbps"] == phy_rate)
    sel_e = (ecdf["cell"] == cell) & (ecdf["class"] == cls) & (ecdf["phy_rate_Mbps"] == phy_rate)
    s, e = summary[sel_s], ecdf[sel_e]
    if s.empty:
        raise KeyError(f"no rows for cell={cell}, class={cls!r}, phy_rate={phy_rate}")

    ns = sorted(s["N_AMR"].unique())
    lams = sorted(s["lambda_tel_Mbps"].unique())
    n_q, lam_q = float(n_amr), float(lam)

    if not ns[0] <= n_q <= ns[-1]:
        LOG.warning("N_AMR=%s outside grid [%s, %s]: clamped (no extrapolation)", n_amr, ns[0], ns[-1])
        n_q = float(np.clip(n_q, ns[0], ns[-1]))
    if not lams[0] <= lam_q <= lams[-1]:
        LOG.warning("lambda_tel=%s outside grid [%s, %s]: clamped (no extrapolation)", lam, lams[0], lams[-1])
        lam_q = float(np.clip(lam_q, lams[0], lams[-1]))

    saturated = (cell in FIFO_CELLS and lam_q > FIFO_SATURATION_MBPS) or \
                (cell in TAS_CELLS and cls == "telemetry" and lam_q > TAS_TELEMETRY_SATURATION_MBPS)
    if saturated:
        lam_q = float(min(lams, key=lambda v: abs(v - lam_q)))

    n_levels = len(dm.QUANTILE_LEVELS)
    cube = np.full((len(ns), len(lams), n_levels + 1), np.nan)
    for i, n in enumerate(ns):
        for j, l in enumerate(lams):
            rows = e[(e["N_AMR"] == n) & (e["lambda_tel_Mbps"] == l)].sort_values("quantile_level")
            ploss = s[(s["N_AMR"] == n) & (s["lambda_tel_Mbps"] == l)]["p_loss"]
            if len(rows) == n_levels and len(ploss) == 1:
                cube[i, j, :n_levels] = rows["delay_ms"].to_numpy()
                cube[i, j, n_levels] = ploss.iloc[0]

    if np.isnan(cube).any():
        LOG.warning("incomplete grid for cell=%s class=%s phy=%s: result is NaN", cell, cls, phy_rate)
        return {"p_loss": float("nan"), "levels": dm.QUANTILE_LEVELS, "delay_ms": np.full(n_levels, np.nan)}

    # Interpolate each quantile horizontally in load, then vertically in fleet size.
    along_lam = _pchip(lams, cube, lam_q, axis=1)
    vec = _pchip(ns, along_lam, n_q, axis=0)
    delay = np.maximum.accumulate(np.clip(vec[:n_levels], 0.0, None))
    return {
        "p_loss": float(np.clip(vec[n_levels], 0.0, 1.0)),
        "levels": dm.QUANTILE_LEVELS,
        "delay_ms": delay,
    }


def _pchip(x, y, xq: float, axis: int):
    if len(x) == 1:
        return np.take(y, 0, axis=axis)
    return PchipInterpolator(np.asarray(x, dtype=float), y, axis=axis, extrapolate=False)(xq)


# --------------------------------------------------------------------------- reference sampler & G8a harness
def flow_rng(run_seed: int, flow_id: str) -> np.random.Generator:
    """Deterministic per-flow PRNG stream isolated by (run_seed, flow_id) (SPEC section 2.1)."""
    flow_hash = zlib.crc32(str(flow_id).encode("utf-8")) & 0xFFFFFFFF
    return np.random.default_rng(np.random.SeedSequence([int(run_seed) & 0xFFFFFFFF, int(flow_hash)]))


def sample_delay(delays_ms: Sequence[float], p_loss: float, *,
                 rng: np.random.Generator,
                 levels: Sequence[float] = dm.QUANTILE_LEVELS,
                 n_draws: int = 1) -> np.ndarray:
    """Three-step stochastic inverse-transform lookup sampler (SPEC-lookup-ner-integration.md section 2.2).

    Draws independent u_loss ~ U(0, 1) and u_lat ~ U(0, 1) from ``rng`` for each message, as a pair, so
    message i always receives the same pair whether messages are drawn in one batch or one at a time
    (the twin draws at send time). Returns delays in ms, with ``np.inf`` where u_loss < p_loss.
    """
    if not (0.0 <= float(p_loss) <= 1.0):
        raise ValueError(f"p_loss must be in [0, 1], got {p_loss}")
    q = np.asarray(levels, dtype=np.float64)
    d = np.asarray(delays_ms, dtype=np.float64)
    if int(n_draws) < 1:
        raise ValueError("n_draws must be >= 1")
    u = rng.random((int(n_draws), 2))  # row i = (u_loss, u_lat) of message i
    u_loss, u_lat = u[:, 0], u[:, 1]
    dropped = u_loss < float(p_loss)
    if np.all(dropped):
        return np.full(int(n_draws), np.inf, dtype=np.float64)
    if q.shape != d.shape or q.ndim != 1 or q.size == 0:
        raise ValueError("levels and delays_ms must be 1-D arrays of equal non-zero length")
    if np.any(np.diff(q) <= 0) or np.any(np.diff(d) < 0):
        raise ValueError("levels must be strictly increasing and delays_ms non-decreasing")
    tau_ms = np.interp(u_lat, q, d)
    return np.where(dropped, np.inf, tau_ms)


def sample_flow_ner(g_s: Sequence[float], delays_ms: Sequence[float], p_loss: float, *,
                    run_seed: int, flow_id: str, lead_ms: float,
                    tick_ms: float = dm.T_PRIMARY_MS, phase_ms: float = 0.0,
                    levels: Sequence[float] = dm.QUANTILE_LEVELS) -> Dict[str, np.ndarray]:
    """Deterministic seeded replay of a message flow through the NER tick grid (SPEC section 2.1-2.2)."""
    g = np.asarray(g_s, dtype=np.float64)
    rng = flow_rng(run_seed, flow_id)
    tau_ms = sample_delay(delays_ms, p_loss, rng=rng, levels=levels, n_draws=g.size)
    dropped = ~np.isfinite(tau_ms)
    a_s = np.where(dropped, np.inf, g + tau_ms / 1000.0)
    c_ps = dm.consumption_instant_ps(dm.to_ps(g), dm._ps(lead_ms), dm._ps(tick_ms), dm._ps(phase_ms))
    c_s = c_ps.astype(np.float64) / dm.PS_PER_S
    return {
        "dropped": dropped,
        "delay_ms": tau_ms,
        "a_s": a_s,
        "c_s": c_s,
        "miss_B": dm.miss_b(g, a_s, lead_ms=lead_ms, tick_ms=tick_ms, phase_ms=phase_ms),
        "staleness_ticks": dm.staleness_ticks(g, a_s, lead_ms=lead_ms, tick_ms=tick_ms, phase_ms=phase_ms),
    }


def dkw_epsilon(n_samples: int, alpha: float) -> float:
    """Dvoretzky-Kiefer-Wolfowitz half-width at two-sided level ``alpha``, plus the 1/n discretization slack."""
    return math.sqrt(math.log(2.0 / alpha) / (2.0 * n_samples)) + 1.0 / n_samples


def verify_g8a(summary: pd.DataFrame, ecdf: pd.DataFrame, *,
               require_full_grid: bool = True,
               mc_draws: int = 100_000,
               seed: int = 20261109,
               mc_family_alpha: float = 0.01) -> Dict[str, object]:
    """Execute the standalone Phase 8 (G8a) lookup-table and twin-ingestion verification suite.

    The Monte Carlo checks run once per key, so their error level is controlled across the whole table:
    each key is tested at ``mc_family_alpha / len(summary)``. A per-key 1% level false-fails about 3 keys
    in 1,920 on a correct table.
    """
    from scipy.stats import norm
    alpha_key = float(mc_family_alpha) / max(len(summary), 1)
    z_loss = float(norm.isf(alpha_key / 2.0))
    # 1. Schema and tail flags
    if list(summary.columns) != SUMMARY_COLUMNS:
        raise RuntimeError(f"G8a.1 schema mismatch in summary: {list(summary.columns)}")
    if list(ecdf.columns) != ECDF_COLUMNS:
        raise RuntimeError(f"G8a.1 schema mismatch in ecdf: {list(ecdf.columns)}")
    expected_keys = len(LOCKED_GRID_CELLS) * len(dm.CLASSES) * len(LOCKED_GRID_NAMRS) * len(LOCKED_GRID_TELS) * len(LOCKED_GRID_PHYS)
    if require_full_grid and len(summary) != expected_keys:
        raise RuntimeError(f"G8a.1 expected {expected_keys} summary rows, got {len(summary)}")
    if summary.duplicated(subset=KEY).any():
        raise RuntimeError("G8a.1 duplicate keys in summary")
    if not set(summary["flag_p99"]).issubset({"OK", "INSUFFICIENT_TAIL_SAMPLES"}):
        raise RuntimeError("G8a.1 invalid flag_p99 values")
    if not set(summary["flag_p99_9"]).issubset({"OK", "INSUFFICIENT_TAIL_SAMPLES"}):
        raise RuntimeError("G8a.1 invalid flag_p99_9 values")

    # 4 & 5 & 6 & 7. Per-key grid reproduction, invariants, offline vs direct, and Monte Carlo
    high_errs: List[float] = []
    low_errs: List[float] = []
    rng_mc = np.random.default_rng(seed)

    for _, row in summary.iterrows():
        key_tuple = tuple(row[k] for k in KEY)
        cell, cls, n_amr, lam, phy = int(row["cell"]), str(row["class"]), int(row["N_AMR"]), float(row["lambda_tel_Mbps"]), int(row["phy_rate_Mbps"])
        p_loss = float(row["p_loss"])
        if not (0.0 <= p_loss <= 1.0):
            raise RuntimeError(f"G8a.1 invalid p_loss={p_loss} at {key_tuple}")

        # 5. Monotone miss rates in D, miss_B <= miss_A, late_arrival >= -1e-12
        for d1, d2 in zip(dm.D_SPECTRUM_MS[:-1], dm.D_SPECTRUM_MS[1:]):
            if float(row[f"miss_A_{d2}ms"]) > float(row[f"miss_A_{d1}ms"]) + 1e-12:
                raise RuntimeError(f"G8a.5 non-monotone miss_A at {key_tuple}: D={d1}->{d2}")
            if float(row[f"miss_B_{d2}ms"]) > float(row[f"miss_B_{d1}ms"]) + 1e-12:
                raise RuntimeError(f"G8a.5 non-monotone miss_B at {key_tuple}: D={d1}->{d2}")
        for d in dm.D_SPECTRUM_MS:
            ma, mb = float(row[f"miss_A_{d}ms"]), float(row[f"miss_B_{d}ms"])
            if mb > ma + 1e-12:
                raise RuntimeError(f"G8a.5 miss_B > miss_A at {key_tuple}, D={d}")
            # Note: in summary, miss_A is the unweighted mean over reps while p_loss is pooled over reps,
            # which can differ by O(1/n_total) when Late_Arrival == 0; check both summary and exact quantile late_arrival.
            if ma - p_loss < -1e-4:
                raise RuntimeError(f"G8a.5 negative late-arrival rate at {key_tuple}, D={d}: {ma} < {p_loss}")

        sub_e = ecdf[
            (ecdf["cell"] == cell)
            & (ecdf["class"] == cls)
            & (ecdf["N_AMR"] == n_amr)
            & np.isclose(ecdf["lambda_tel_Mbps"], lam)
            & (ecdf["phy_rate_Mbps"] == phy)
        ].sort_values("quantile_level")

        n_drops = int(row["n_Drop_Queue"] + row["n_Drop_Retry"] + row["n_Drop_Other"])
        n_late_term = int(row["n_Late_Termination"])
        n_deliv = int(row["n_total"]) - n_drops - n_late_term
        if n_deliv <= 0:
            continue

        if len(sub_e) != len(dm.QUANTILE_LEVELS):
            raise RuntimeError(f"G8a.1 expected 25 ECDF rows at {key_tuple}, got {len(sub_e)}")
        delays = sub_e["delay_ms"].to_numpy(dtype=np.float64)
        if not np.all(np.isfinite(delays)) or np.any(delays < 0) or np.any(np.diff(delays) < 0):
            raise RuntimeError(f"G8a.5 invalid or crossing quantiles at {key_tuple}")

        # 4. Grid node reproduction via interpolate() when the slice grid is complete
        interp = interpolate(summary, ecdf, cell=cell, cls=cls, phy_rate=phy, n_amr=n_amr, lam=lam)
        if np.all(np.isfinite(interp["delay_ms"])):
            if abs(float(interp["p_loss"]) - p_loss) > 1e-12 or np.max(np.abs(interp["delay_ms"] - delays)) > 1e-12:
                raise RuntimeError(f"G8a.4 grid node reproduction failed at {key_tuple}")

        # 6. Offline estimate vs direct measurement
        p_terminal = (n_drops + n_late_term) / float(row["n_total"])
        for d in dm.D_SPECTRUM_MS:
            est_a = dm.miss_a_from_quantiles(float(d), delays, p_loss=p_terminal)
            est_b = dm.miss_b_from_quantiles(float(d), float(dm.T_PRIMARY_MS), delays, p_loss=p_terminal)
            if est_a - p_terminal < -1e-12 or est_b - p_terminal < -1e-12 or est_b > est_a + 1e-12:
                raise RuntimeError(f"G8a.5 quantile evaluator invariant violated at {key_tuple}, D={d}")
            for direct, est in ((float(row[f"miss_A_{d}ms"]), est_a), (float(row[f"miss_B_{d}ms"]), est_b)):
                err = abs(est - direct)
                if direct >= 0.05:
                    high_errs.append(err)
                else:
                    low_errs.append(err)

        # 7. Monte Carlo DKW and binomial checks
        if mc_draws > 0:
            draws = sample_delay(delays, p_loss, rng=rng_mc, n_draws=mc_draws)
            lost_mask = ~np.isfinite(draws)
            emp_loss = float(np.mean(lost_mask))
            # family-wise normal tolerance around p_loss (z set from alpha_key)
            loss_tol = z_loss * math.sqrt(max(p_loss * (1.0 - p_loss), 1.0 / mc_draws) / mc_draws) + (2.0 / mc_draws)
            if abs(emp_loss - p_loss) > loss_tol:
                raise RuntimeError(f"G8a.7 MC loss {emp_loss:.5f} outside tolerance of {p_loss:.5f} at {key_tuple}")
            deliv_draws = np.sort(draws[~lost_mask])
            if deliv_draws.size >= 100:
                eps_dkw = dkw_epsilon(deliv_draws.size, alpha_key)
                # Right-continuous and left-continuous empirical CDF at each knot delay
                cdf_hi = np.searchsorted(deliv_draws, delays, side="right") / deliv_draws.size
                cdf_lo = np.searchsorted(deliv_draws, delays, side="left") / deliv_draws.size
                levels_arr = np.asarray(dm.QUANTILE_LEVELS, dtype=np.float64)
                if np.any(levels_arr < cdf_lo - eps_dkw) or np.any(levels_arr > cdf_hi + eps_dkw):
                    raise RuntimeError(f"G8a.7 MC quantile draws violated the family-wise DKW bound ({eps_dkw:.5f}) at {key_tuple}")

    high_mean = float(np.mean(high_errs)) if high_errs else 0.0
    high_max = float(np.max(high_errs)) if high_errs else 0.0
    low_mean = float(np.mean(low_errs)) if low_errs else 0.0
    low_max = float(np.max(low_errs)) if low_errs else 0.0

    if high_errs and (high_mean > 0.025 or high_max > 0.050):
        raise RuntimeError(f"G8a.6 high-miss offline error exceeded tolerance: mean={high_mean:.4f}, max={high_max:.4f}")
    if low_errs and (low_mean > 0.005 or low_max > 0.015):
        raise RuntimeError(f"G8a.6 low-miss offline error exceeded tolerance: mean={low_mean:.4f}, max={low_max:.4f}")

    # 2. Seeded replay determinism and stream isolation
    first_ecdf = ecdf.head(len(dm.QUANTILE_LEVELS)).sort_values("quantile_level")["delay_ms"].to_numpy()
    if len(first_ecdf) == len(dm.QUANTILE_LEVELS):
        g_test = np.linspace(5.0, 55.0, 128)
        r1 = sample_flow_ner(g_test, first_ecdf, 0.1, run_seed=seed, flow_id="amr[0]->fms", lead_ms=50.0)
        r2 = sample_flow_ner(g_test, first_ecdf, 0.1, run_seed=seed, flow_id="amr[0]->fms", lead_ms=50.0)
        r_diff_seed = sample_flow_ner(g_test, first_ecdf, 0.1, run_seed=seed + 1, flow_id="amr[0]->fms", lead_ms=50.0)
        r_diff_flow = sample_flow_ner(g_test, first_ecdf, 0.1, run_seed=seed, flow_id="amr[1]->fms", lead_ms=50.0)
        for k in ("dropped", "c_s", "miss_B", "staleness_ticks"):
            if not np.array_equal(r1[k], r2[k]):
                raise RuntimeError(f"G8a.2 seeded replay mismatch on {k}")
        if not np.allclose(r1["delay_ms"], r2["delay_ms"], equal_nan=True):
            raise RuntimeError("G8a.2 seeded replay mismatch on delay_ms")
        if np.allclose(r1["delay_ms"], r_diff_seed["delay_ms"], equal_nan=True):
            raise RuntimeError("G8a.2 different seeds produced identical sequences")
        if np.allclose(r1["delay_ms"], r_diff_flow["delay_ms"], equal_nan=True):
            raise RuntimeError("G8a.2 different flow_ids produced identical sequences")

    return {
        "n_keys": len(summary),
        "high_miss_count": len(high_errs),
        "high_miss_mean_err": high_mean,
        "high_miss_max_err": high_max,
        "low_miss_count": len(low_errs),
        "low_miss_mean_err": low_mean,
        "low_miss_max_err": low_max,
    }


# --------------------------------------------------------------------------- CLI
def main(argv: Optional[list] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--packets", help="Stage 1: per-packet CSV")
    group.add_argument("--sca-dir", help="Stage 2: directory of campaign .sca files")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--base-seed", type=int, default=0, help="seed of the per-replication tick phase")
    p.add_argument("--warmup", type=float, default=dm.WARMUP_S)
    p.add_argument("--sim-limit", type=float, default=dm.SIM_LIMIT_S)
    p.add_argument("--expected-reps", type=int, default=22,
                   help="minimum Stage-2 repetition count per key (0 disables the check); seeds must run "
                        "contiguously from 0 and all six cells of a slice must share the same count")
    p.add_argument("--domain-delay", action="store_true",
                   help="also write lookup_domain_delay.csv (per-run wireless / switch / serialization "
                        "delay means from the sinks' statistic blocks; Stage 2 only)")
    p.add_argument("--verify-g8a", action="store_true",
                   help="run the Phase 8 (G8a) lookup-table and inverse-transform sampler verification suite")
    p.add_argument("--allow-partial-grid", action="store_true",
                   help="allow Stage-2 input that does not contain the full locked factorial grid")
    p.add_argument("--sample", metavar="CELL,N,LAMBDA,PHY",
                   help="keep one key only: the 1-cell/1-N/1-lambda ingestion prototype (checklist C3)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.packets:
        packets = read_packets(args.packets)
        if args.sample:
            cell, n, lam, phy = args.sample.split(",")
            packets = packets[
                (packets["cell"] == int(cell))
                & (packets["N_AMR"] == int(n))
                & np.isclose(packets["lambda_tel_Mbps"], float(lam))
                & (packets["phy_rate_Mbps"] == int(phy))
            ]
            if packets.empty:
                raise SystemExit("--sample matches no rows")
        summary, ecdf = build_tables(packets, args.base_seed, args.warmup, args.sim_limit)
    else:
        summary, ecdf = build_tables_from_sca(
            Path(args.sca_dir), expected_reps=args.expected_reps or None,
            require_full_grid=not args.allow_partial_grid and not bool(args.sample))
        if args.sample:
            cell, n, lam, phy = args.sample.split(",")
            mask_s = (
                (summary["cell"] == int(cell))
                & (summary["N_AMR"] == int(n))
                & np.isclose(summary["lambda_tel_Mbps"], float(lam))
                & (summary["phy_rate_Mbps"] == int(phy))
            )
            mask_e = (
                (ecdf["cell"] == int(cell))
                & (ecdf["N_AMR"] == int(n))
                & np.isclose(ecdf["lambda_tel_Mbps"], float(lam))
                & (ecdf["phy_rate_Mbps"] == int(phy))
            )
            summary, ecdf = summary[mask_s], ecdf[mask_e]
            if summary.empty:
                raise SystemExit("--sample matches no rows")

    write_tables(summary, ecdf, args.out_dir)
    if args.domain_delay:
        if not args.sca_dir:
            raise SystemExit("--domain-delay needs --sca-dir")
        domain_table = build_domain_delay_table(Path(args.sca_dir))
        domain_table.to_csv(Path(args.out_dir) / "lookup_domain_delay.csv", index=False)
        LOG.info("wrote %d domain-delay rows to %s", len(domain_table), args.out_dir)
    if args.verify_g8a:
        report = verify_g8a(
            summary, ecdf,
            require_full_grid=not args.allow_partial_grid and not bool(args.sample) and not bool(args.packets),
        )
        LOG.info("G8a verification passed: %s", report)
    LOG.info("wrote %d summary rows and %d ecdf rows to %s", len(summary), len(ecdf), args.out_dir)


if __name__ == "__main__":
    main()
