"""Lookup-table export for the digital twin's NER engine (decisions.md section 5, Q3).

Supports TWO ingestion modes:
1. Stage 1 (--packets): Per-packet CSV table (used by the 41-test unit suite and pilot debug runs).
2. Stage 2 (--sca-dir): Campaign-scale OMNeT++ .sca files produced by DeadlineSink and INET MAC/switch queues across Cell1_Sweep..Cell6_Sweep (4,800 runs), enforcing the strict Packet Conservation Audit Gate (SPEC-lookup-ner-integration.md section 1.2).

Also provides ``interpolate`` (quantile-space monotone PCHIP along N_AMR and
lambda_tel, non-crossing guard, delays >= 0, saturation nearest-neighbour clamp,
no extrapolation with a logged warning; decisions.md section 5.4).
"""
from __future__ import annotations

import argparse
import glob
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

import deadline_metrics as dm

LOG = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"
KEY = ["cell", "class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"]
PACKET_COLUMNS = KEY + ["rep", "g_s", "a_s", "drop_cause"]
HORIZON_LEAD_MS = max(dm.D_SPECTRUM_MS)      # common 100 ms horizon filter across all D
TAIL_N_P99 = 10**4
TAIL_N_P999 = 10**5

FIFO_CELLS = (1, 2)
TAS_CELLS = (5, 6)
FIFO_SATURATION_MBPS = 100.0       # decisions.md section 5.4 item 4
TAS_TELEMETRY_SATURATION_MBPS = 44.8

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
    + ["n_reps", "n_total", "p_loss", "n_Drop_Queue", "n_Drop_Retry", "n_Drop_Other"]
    + [f"miss_A_{d}ms" for d in dm.D_SPECTRUM_MS]
    + [f"miss_B_{d}ms" for d in dm.D_SPECTRUM_MS]
    + ["ci95_miss_B", "lat_p50", "lat_p90", "lat_p95", "lat_p99", "lat_p99_9",
       "insufficient_tail_samples", "schema_version"]
)
ECDF_COLUMNS = KEY + ["quantile_level", "delay_ms"]


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
    summary_rows, ecdf_rows = [], []
    levels = np.array(dm.QUANTILE_LEVELS)
    idx = {lvl: i for i, lvl in enumerate(dm.QUANTILE_LEVELS)}

    for key, grp in packets.groupby(KEY, sort=True):
        cell, cls, n_amr, lam, phy = key
        if cls not in dm.NOMINAL_D_MS:
            raise ValueError(f"unknown traffic class {cls!r}")
        nominal = dm.NOMINAL_D_MS[cls]

        rates = {("A", d): [] for d in dm.D_SPECTRUM_MS} | {("B", d): [] for d in dm.D_SPECTRUM_MS}
        bins = {"n_valid": 0, "Drop_Queue": 0, "Drop_Retry": 0, "Drop_Other": 0}
        pooled = []

        reps = sorted(grp["rep"].unique())
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
        )
        for d in dm.D_SPECTRUM_MS:
            row[f"miss_A_{d}ms"] = _nanmean(rates[("A", d)])
            row[f"miss_B_{d}ms"] = _nanmean(rates[("B", d)])

        row.update(
            ci95_miss_B=dm.student_t_halfwidth(rates[("B", nominal)]),
            lat_p50=qs[idx[0.50]],
            lat_p90=qs[idx[0.90]],
            lat_p95=qs[idx[0.95]],
            lat_p99=qs[idx[0.99]],
            lat_p99_9=qs[idx[0.999]],
            insufficient_tail_samples=bool(pooled.size < TAIL_N_P99 or pooled.size < TAIL_N_P999),
            schema_version=SCHEMA_VERSION,
        )
        summary_rows.append(row)

        if pooled.size:
            for lvl, dly in zip(dm.QUANTILE_LEVELS, qs):
                ecdf_rows.append({**dict(zip(KEY, key)), "quantile_level": lvl, "delay_ms": float(dly)})

    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    ecdf = pd.DataFrame(ecdf_rows, columns=ECDF_COLUMNS)
    return summary, ecdf


# --------------------------------------------------------------------------- Stage 2 input (.sca campaign files)
def parse_sca_file(sca_path: Path) -> Tuple[Dict[str, str], Dict[Tuple[str, str], float]]:
    """Parse itervar/param headers and scalar (module, name) -> value from an OMNeT++ .sca file."""
    attrs: Dict[str, str] = {}
    scalars: Dict[Tuple[str, str], float] = {}
    with open(sca_path, "r", encoding="utf-8", errors="replace") as f:
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


def build_tables_from_sca(sca_dir: Path, strict_conservation: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Ingest campaign .sca files produced by DeadlineSink and build (lookup_summary, lookup_ecdf)."""
    sca_files = sorted(Path(sca_dir).glob("*.sca"))
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
        lam = TEL_INTERVAL_TO_MBPS.get(tel_str, 22.4)
        phy_str = attrs.get("phyRate", "54Mbps").replace("Mbps", "").strip('"')
        phy = int(float(phy_str))
        rep = int(attrs.get("repetition", 0))

        # Aggregate DeadlineSink scalars per traffic class (orders sits across amr[0..N-1].app[1].sink)
        for cls in ("orders", "dds", "state", "telemetry"):
            sink_mods = [mod for (mod, sname) in scalars if sname == "n_valid_delivered" and (
                (cls == "orders" and ".amr[" in mod and ".app[1].sink" in mod) or
                (cls == "state" and mod.endswith(".fms.app[0].sink")) or
                (cls == "telemetry" and mod.endswith(".fms.app[1].sink")) or
                (cls == "dds" and mod.endswith(".fms.app[2].sink"))
            )]
            if not sink_mods:
                continue

            n_rx_total = int(sum(scalars.get((m, "n_received_total"), 0.0) for m in sink_mods))
            n_warmup = int(sum(scalars.get((m, "n_filtered_warmup"), 0.0) for m in sink_mods))
            n_horizon = int(sum(scalars.get((m, "n_filtered_horizon"), 0.0) for m in sink_mods))
            n_deliv = int(sum(scalars.get((m, "n_valid_delivered"), 0.0) for m in sink_mods))

            if strict_conservation and (n_rx_total != n_deliv + n_warmup + n_horizon):
                raise RuntimeError(
                    f"Sink conservation failed in {sca_path.name} ({cls}): "
                    f"n_received_total={n_rx_total} != {n_deliv}+{n_warmup}+{n_horizon}"
                )

            rec = {
                "cell": cell,
                "class": cls,
                "N_AMR": n_amr,
                "lambda_tel_Mbps": lam,
                "phy_rate_Mbps": phy,
                "rep": rep,
                "n_deliv": n_deliv,
                "n_drop_queue": 0,
                "n_drop_retry": 0,
                "n_drop_other": 0,
            }
            for d in dm.D_SPECTRUM_MS:
                rec[f"n_miss_A_{d}ms"] = int(sum(scalars.get((m, f"n_miss_A_{d}ms"), 0.0) for m in sink_mods))
                rec[f"n_miss_B_{d}ms"] = int(sum(scalars.get((m, f"n_miss_B_{d}ms"), 0.0) for m in sink_mods))

            for lvl in levels:
                q_key = f"ecdf_q_{lvl:.3f}"
                vals = [scalars[(m, q_key)] for m in sink_mods if (m, q_key) in scalars]
                rec[q_key] = float(np.mean(vals)) if vals else float("nan")

            records.append(rec)

    df_runs = pd.DataFrame(records)
    summary_rows, ecdf_rows = [], []
    idx = {lvl: i for i, lvl in enumerate(levels)}

    for key, grp in df_runs.groupby(KEY, sort=True):
        cell, cls, n_amr, lam, phy = key
        nominal = dm.NOMINAL_D_MS[cls]
        n_reps = len(grp)

        n_deliv_total = int(grp["n_deliv"].sum())
        n_drop_q = int(grp["n_drop_queue"].sum())
        n_drop_r = int(grp["n_drop_retry"].sum())
        n_drop_o = int(grp["n_drop_other"].sum())
        drops = n_drop_q + n_drop_r + n_drop_o
        n_total = n_deliv_total + drops

        qs = [float(grp[f"ecdf_q_{lvl:.3f}"].mean()) for lvl in levels]

        row = dict(zip(KEY, key))
        row.update(
            n_reps=n_reps,
            n_total=n_total,
            p_loss=(drops / n_total) if n_total else float("nan"),
            n_Drop_Queue=n_drop_q,
            n_Drop_Retry=n_drop_r,
            n_Drop_Other=n_drop_o,
        )

        rep_totals = grp["n_deliv"] + grp["n_drop_queue"] + grp["n_drop_retry"] + grp["n_drop_other"]
        rep_drops = grp["n_drop_queue"] + grp["n_drop_retry"] + grp["n_drop_other"]

        for d in dm.D_SPECTRUM_MS:
            rates_a = ((grp[f"n_miss_A_{d}ms"] + rep_drops) / rep_totals).to_numpy(dtype=float)
            rates_b = ((grp[f"n_miss_B_{d}ms"] + rep_drops) / rep_totals).to_numpy(dtype=float)
            row[f"miss_A_{d}ms"] = _nanmean(rates_a)
            row[f"miss_B_{d}ms"] = _nanmean(rates_b)
            if d == nominal:
                nom_rates_b = rates_b

        row.update(
            ci95_miss_B=dm.student_t_halfwidth(nom_rates_b),
            lat_p50=qs[idx[0.50]],
            lat_p90=qs[idx[0.90]],
            lat_p95=qs[idx[0.95]],
            lat_p99=qs[idx[0.99]],
            lat_p99_9=qs[idx[0.999]],
            insufficient_tail_samples=bool(n_deliv_total < TAIL_N_P99 or n_deliv_total < TAIL_N_P999),
            schema_version=SCHEMA_VERSION,
        )
        summary_rows.append(row)

        if n_deliv_total > 0:
            for lvl, dly in zip(levels, qs):
                ecdf_rows.append({**dict(zip(KEY, key)), "quantile_level": lvl, "delay_ms": float(dly)})

    return pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS), pd.DataFrame(ecdf_rows, columns=ECDF_COLUMNS)


def _nanmean(values) -> float:
    x = np.asarray(values, dtype=float)
    return float(np.nanmean(x)) if np.isfinite(x).any() else float("nan")


# --------------------------------------------------------------------------- output
def write_tables(summary: pd.DataFrame, ecdf: pd.DataFrame, out_dir) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s_csv = summary.copy()
    s_csv["insufficient_tail_samples"] = s_csv["insufficient_tail_samples"].map({True: "true", False: "false"})
    s_csv.to_csv(out / "lookup_summary.csv", index=False)
    ecdf.to_csv(out / "lookup_ecdf.csv", index=False)
    summary.to_json(out / "lookup_summary.json", orient="records", indent=2)
    ecdf.to_json(out / "lookup_ecdf.json", orient="records", indent=2)


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
        summary, ecdf = build_tables_from_sca(Path(args.sca_dir))
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
    LOG.info("wrote %d summary rows and %d ecdf rows to %s", len(summary), len(ecdf), args.out_dir)


if __name__ == "__main__":
    main()
