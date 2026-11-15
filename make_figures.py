#!/usr/bin/env python3
"""Presentation figures for the Matrix Factory network study.

Reads the exporter outputs (``lookup_summary.csv``, ``lookup_ecdf.csv``,
``lookup_replications.csv``, ``lookup_domain_delay.csv``, ``bottleneck_migration.csv``)
and, optionally, two launcher manifests, then writes slide-ready figures.
Every figure is skipped with a warning if its input is missing, so the script works
on a partial grid and on whatever the campaign has produced so far.

Examples
--------
    # everything the dry-run evidence supports
    python make_figures.py --lookup-dir evidence/05_dry_run_opt/lookup --out figures \
        --manifest-base evidence/05_dry_run/manifest.csv \
        --manifest-opt  evidence/05_dry_run_opt/manifest.csv

    # only some figures, as PNG + PDF, for a chosen operating point
    python make_figures.py --lookup-dir evidence/05_campaign/lookup --out figures \
        --only F04 F08 --n 20 --point 80,12,22.4 --format png pdf

Figures
-------
F01 design_overview      2x3 treatment matrix + traffic-class table
F02 capacity             analytic wireless utilization vs fleet size (docs/capacity.md)
F03 frame_sizes          wire time vs TAS windows; VDA 5050 message sizes vs MTU
F04 load_sweep           metric vs telemetry load, per class, per PHY (the "knee")
F05 radio_scaling        metric vs fleet size N, per class, per PHY
F06 fingerprint          cell x class heatmaps at chosen operating points
F07 bottleneck_map       dominant-bottleneck classification over (N, load, PHY)
F08 latency_ecdf         delay ECDFs per cell at a chosen operating point
F09 domain_delay         stacked wireless / switch / wire delay shares
F10 seed_strip           per-seed scatter (shows variance and collapse outliers)
F11 effect_sizes         paired treatment contrasts with 95% CI
F12 runtime_speedup      measured wall time, baseline vs optimized
F13 surface3d            3-D view of the metric over (N, load): CSMA vs scheduled
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle  # noqa: E402
from mpl_toolkits.mplot3d import Axes3D  # noqa: E402,F401

# --------------------------------------------------------------------------- constants
CELLS: Dict[int, Tuple[str, str]] = {
    1: ("CSMA", "FIFO"), 2: ("Scheduled", "FIFO"),
    3: ("CSMA", "Priority"), 4: ("Scheduled", "Priority"),
    5: ("CSMA", "TAS"), 6: ("Scheduled", "TAS"),
}
WIRED_COLOR = {"FIFO": "#D55E00", "Priority": "#0072B2", "TAS": "#009E73"}
RADIO_STYLE = {"CSMA": dict(ls="-", marker="o"), "Scheduled": dict(ls="--", marker="s")}
CLASSES = ["dds", "state", "orders", "telemetry"]
NOMINAL_D = {"dds": 5, "state": 50, "orders": 50, "telemetry": 100}
CLASS_LABEL = {"dds": "DDS (D=5 ms)", "state": "State (D=50 ms)",
               "orders": "Orders (D=50 ms)", "telemetry": "Telemetry (D=100 ms)"}
TEL_MBPS = {"2000us": 22.4, "996us": 45.0, "747us": 60.0, "600us": 74.7,
            "527us": 85.0, "472us": 95.0, "407us": 110.0, "300us": 149.3}
DOMAIN_COLOR = {"wireless": "#D55E00", "wired_switch": "#0072B2", "wire_serialization": "#999999"}
DOMAIN_LABEL = {"wireless": "Wi-Fi hop (MAC wait + airtime)", "wired_switch": "Switch queue + gates",
                "wire_serialization": "Wire serialization + propagation"}
BOTTLENECK_STYLE = {  # label -> (colour, legend text)
    "none_or_uncongested": ("#E0E0E0", "none / uncongested"),
    "wired": ("#0072B2", "wired"),
    "wired_tas_penalty": ("#56B4E9", "wired (TAS penalty)"),
    "wireless": ("#D55E00", "wireless"),
    "scheduled_radio_penalty": ("#E69F00", "scheduled-radio penalty"),
    "unexplained_radio_penalty": ("#CC79A7", "unexplained radio penalty"),
    "structural_schedule_wait": ("#F0E442", "structural TDMA wait"),
    "mixed_or_uncertain": ("#8C8C8C", "mixed / uncertain"),
}
METRIC_LABEL = {"miss_B": "Deadline-miss rate, Definition B (%)",
                "miss_A": "Deadline-miss rate, Definition A (%)",
                "p_loss": "Physical packet loss (%)",
                "p99": "p99 end-to-end latency (ms)",
                "p50": "median end-to-end latency (ms)"}
PERCENT_METRICS = {"miss_B", "miss_A", "p_loss"}


# --------------------------------------------------------------------------- helpers
def _lum(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cell_label(c: int) -> str:
    radio, wired = CELLS[c]
    return f"C{c}: {radio} + {wired}"


def cell_kwargs(c: int) -> dict:
    radio, wired = CELLS[c]
    return dict(color=WIRED_COLOR[wired], **RADIO_STYLE[radio])


def cell_legend() -> List[Line2D]:
    return [Line2D([0], [0], label=cell_label(c), lw=2, ms=6, **cell_kwargs(c)) for c in CELLS]


def metric_values(df: pd.DataFrame, cls: str, metric: str) -> pd.Series:
    if metric in ("miss_A", "miss_B"):
        return df[f"{metric}_{NOMINAL_D[cls]}ms"] * 100.0
    if metric == "p_loss":
        return df["p_loss"] * 100.0
    if metric == "p99":
        return df["lat_p99"]
    if metric == "p50":
        return df["lat_p50"]
    raise ValueError(f"unknown metric {metric!r}")


def fmt_lambda(x: float) -> str:
    return f"{x:g}"


_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
         10: 2.228, 12: 2.179, 14: 2.145, 16: 2.120, 20: 2.086, 25: 2.060, 30: 2.042}


def t975(df: int) -> float:
    """Two-sided 95% Student-t critical value."""
    try:
        from scipy import stats
        return float(stats.t.ppf(0.975, df))
    except Exception:
        keys = sorted(_T975)
        return _T975[max(k for k in keys if k <= df)] if df >= keys[0] else _T975[keys[0]]


def stamp(fig, summary: Optional[pd.DataFrame], extra: str = "") -> None:
    text = ""
    if summary is not None and "n_reps" in summary and not summary.empty:
        lo, hi = int(summary["n_reps"].min()), int(summary["n_reps"].max())
        if lo == hi == 3:
            text = "R = 3 seeds per point (uniform, indicative while R < 22)."
        else:
            r = f"R = {lo}" if lo == hi else f"R = {lo}–{hi}"
            text = f"{r} seeds per point (indicative while R < 22)."
    if extra:
        text = f"{text} {extra}".strip()
    if text:
        fig.text(0.995, 0.995, text, ha="right", va="top", fontsize=8, color="#666666")


def assert_complete_grid(
    summary: Optional[pd.DataFrame],
    expected_loads: Optional[Sequence[float]] = None,
) -> None:
    """Verify uniform replication count and zero missing cells in the Cartesian summary grid."""
    if summary is None or summary.empty:
        raise RuntimeError("completeness gate failed: lookup_summary is empty")
    lo, hi = int(summary["n_reps"].min()), int(summary["n_reps"].max())
    if lo != hi or lo < 1:
        raise RuntimeError(f"completeness gate failed: non-uniform replication count n_reps in [{lo}, {hi}]")
    ns = sorted(int(v) for v in summary["N_AMR"].unique())
    phys = sorted(int(v) for v in summary["phy_rate_Mbps"].unique())
    lams = sorted(round(float(v), 3) for v in summary["lambda_tel_Mbps"].unique())
    if len(ns) < 3 or len(phys) != 2 or len(lams) < 4:
        raise RuntimeError(
            f"completeness gate failed: insufficient grid dimensions N={ns}, phy={phys}, loads={lams}"
        )
    if expected_loads:
        wanted = sorted(round(float(v), 3) for v in expected_loads)
        if len(lams) != len(wanted) or not all(any(abs(a - b) <= 0.15 for a in lams) for b in wanted):
            raise RuntimeError(f"completeness gate failed: expected loads {wanted}, got {lams}")
    expected_keys = {
        (c, cls, n, lam, phy)
        for c in sorted(CELLS)
        for cls in CLASSES
        for n in ns
        for lam in lams
        for phy in phys
    }
    observed_keys = {
        (int(r["cell"]), str(r["class"]), int(r["N_AMR"]), round(float(r["lambda_tel_Mbps"]), 3), int(r["phy_rate_Mbps"]))
        for _, r in summary.iterrows()
    }
    missing = sorted(expected_keys - observed_keys)
    if missing:
        raise RuntimeError(f"completeness gate failed: {len(missing)} missing grid entries, e.g. {missing[:3]}")


def save(fig, name: str, args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for fmt in args.format:
        path = out / f"{name}.{fmt}"
        fig.savefig(path, dpi=args.dpi, bbox_inches="tight", facecolor="white")
        print(f"  wrote {path}")
    plt.close(fig)


def read_csv(directory: Path, name: str) -> Optional[pd.DataFrame]:
    path = directory / name
    if not path.exists():
        print(f"  [skip-input] {path} not found", file=sys.stderr)
        return None
    return pd.read_csv(path)


def has_point(s: pd.DataFrame, n: float, phy: float, lam: float) -> bool:
    m = (s["N_AMR"] == n) & (s["phy_rate_Mbps"] == phy) & np.isclose(s["lambda_tel_Mbps"], lam)
    return bool(m.any())


def default_points(s: pd.DataFrame) -> List[Tuple[int, int, float]]:
    ns = sorted(s["N_AMR"].unique())
    phys = sorted(s["phy_rate_Mbps"].unique())
    lams = sorted(s["lambda_tel_Mbps"].unique())
    cand = [(ns[0], max(phys), lams[0]), (ns[-1], max(phys), lams[-1]),
            (ns[-1], min(phys), lams[0]), (ns[-1], min(phys), lams[-1])]
    out: List[Tuple[int, int, float]] = []
    for n, p, l in cand:
        if has_point(s, n, p, l) and (int(n), int(p), float(l)) not in out:
            out.append((int(n), int(p), float(l)))
    return out


def parse_points(raw: Optional[Sequence[str]], s: pd.DataFrame) -> List[Tuple[int, int, float]]:
    if not raw:
        return default_points(s)
    pts = []
    for item in raw:
        n, p, l = item.split(",")
        pts.append((int(n), int(p), float(l)))
    return pts


def pick_n(s: pd.DataFrame, requested: Optional[int]) -> int:
    if requested is not None:
        return int(requested)
    counts = s.groupby("N_AMR")["lambda_tel_Mbps"].nunique()
    best = counts.max()
    return int(counts[counts == best].index.max())


def point_title(n: int, phy: int, lam: float) -> str:
    return f"N={n} AMRs · {phy} Mbps PHY · telemetry {fmt_lambda(lam)} Mbps"


# --------------------------------------------------------------------------- F01
def fig_design_overview(ctx) -> None:
    fig = plt.figure(figsize=(13, 7.2))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.15, 1], hspace=0.28)
    ax = fig.add_subplot(gs[0])
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.45, 4.4)
    ax.axis("off")
    ax.set_title("Treatments: a 2 × 3 factorial design. Everything except the two factors is identical",
                 fontsize=13, fontweight="bold", loc="left")
    cols = [("FIFO", "one 80-packet queue"), ("Priority", "strict priority\n4 × 20 queues"),
            ("TAS", "802.1Qbv gates\n4 × 20 queues, 1 ms cycle")]
    rows = [("CSMA", "CSMA/CA (802.11 DCF)\ncontention-based"),
            ("Scheduled", "ScheduledDcf (TDMA)\nconflict-free slots")]
    x0, y0, w, h = 2.6, 0.2, 2.35, 1.45
    for j, (name, sub) in enumerate(cols):
        ax.text(x0 + j * (w + 0.1) + w / 2, 3.85, f"{name}\n{sub}", ha="center", va="center",
                fontsize=9.5, color=WIRED_COLOR[name], fontweight="bold")
    for i, (name, sub) in enumerate(rows):
        yy = y0 + (1 - i) * (h + 0.15)
        ax.text(0.15, yy + h / 2, sub, ha="left", va="center", fontsize=10.5, fontweight="bold")
        for j, (wired, _) in enumerate(cols):
            c = [k for k, v in CELLS.items() if v == (name, wired)][0]
            ax.add_patch(FancyBboxPatch((x0 + j * (w + 0.1), yy), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                        fc=WIRED_COLOR[wired], ec="black", alpha=0.18 if name == "CSMA" else 0.38))
            ax.text(x0 + j * (w + 0.1) + w / 2, yy + h / 2, f"Cell {c}", ha="center", va="center",
                    fontsize=15, fontweight="bold")
    ax.text(0.15, -0.3, "Shared across cells: traffic, AMR placement, seeds (paired runs), buffer budget, deadlines.",
            fontsize=9.5, color="#444444", va="bottom")

    ax2 = fig.add_subplot(gs[1])
    ax2.axis("off")
    data = [["Orders", "FMS → AMR", "600 B", "5 Hz / AMR (exp.)", "50 ms", "KILL"],
            ["DDS", "Station → FMS", "200 B", "100 Hz / station (±5%)", "5 ms", "KILL"],
            ["State", "AMR → FMS", "1000 B", "10 Hz / AMR (90–110 ms)", "50 ms", "ZOH"],
            ["Telemetry", "Station → FMS", "1400 B", "Poisson, 22.4–149.3 Mbps total", "100 ms", "ZOH"]]
    tbl = ax2.table(cellText=data, colLabels=["Class", "Direction", "Payload", "Rate", "Deadline", "Late rule"],
                    loc="upper center", cellLoc="center", colWidths=[0.12, 0.16, 0.10, 0.30, 0.11, 0.11])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10.5)
    tbl.scale(1, 1.75)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#333333")
            cell.set_text_props(color="white", fontweight="bold")
    ax2.text(0.5, 0.02,
             "Grid: N ∈ {5, 10, 20, 40, 80} AMRs  ×  PHY ∈ {54, 12} Mbps  ×  8 telemetry loads  ×  6 cells  ×  22 seeds"
             "  =  10,560 runs of 60 simulated seconds (5 s warm-up)",
             transform=ax2.transAxes, ha="center", fontsize=10.5, fontweight="bold")
    save(fig, "F01_design_overview", ctx.args)


# --------------------------------------------------------------------------- F02
def fig_capacity(ctx) -> None:
    ns = np.array([5, 10, 20, 40, 80])
    # docs/capacity.md (collision-free lower bound); 6 Mbps at N=80 is ">100%", plotted from the linear model.
    util = {54: [2, 5, 9, 18, 37], 24: [4, 7, 14, 29, 57], 12: [6, 12, 24, 48, 95], 6: [11, 21, 43, 86, 172]}
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    palette = {54: "#009E73", 24: "#56B4E9", 12: "#D55E00", 6: "#7A0019"}
    for phy, vals in util.items():
        ax.plot(ns, vals, marker="o", lw=2.2, color=palette[phy], label=f"{phy} Mbps")
        ax.annotate(f"{vals[-1] if phy != 6 else '>100'}%", (ns[-1], vals[-1]), textcoords="offset points",
                    xytext=(8, -3), fontsize=9, color=palette[phy])
    ax.axhline(100, color="black", ls=":", lw=1.2)
    ax.text(5.2, 103, "channel saturated", fontsize=9)
    ax.axvspan(10, 20, color="#999999", alpha=0.15)
    ax.text(14.1, 150, "twin range\n(13 agents)", ha="center", fontsize=9, color="#444444")
    ax.set_xscale("log", base=2)
    ax.set_xticks(ns)
    ax.set_xticklabels(ns)
    ax.set_xlim(4.2, 110)
    ax.set_ylim(0, 185)
    ax.set_xlabel("Fleet size N (AMRs)")
    ax.set_ylabel("Wireless channel utilization (%)")
    ax.set_title("Why 12 Mbps and N = 80 are in the grid: 54 Mbps never loads the radio",
                 fontsize=12.5, fontweight="bold", loc="left")
    ax.legend(title="802.11 PHY rate", frameon=False)
    ax.grid(alpha=0.25)
    stamp(fig, None, "Analytic collision-free lower bound (docs/capacity.md).")
    save(fig, "F02_capacity", ctx.args)


# --------------------------------------------------------------------------- F03
def fig_frame_sizes(ctx) -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw=dict(width_ratios=[1.1, 1]))
    names = ["DDS\n270 B wire", "Orders\n666 B wire", "State\n1070 B wire", "Telemetry\n1470 B wire",
             "Orders at\n1500 B MTU\n(hypothetical)"]
    frame_us = [21.6, 53.28, 85.6, 117.6, 123.36]
    window_us = [200, 100, 200, 500, 100]
    y = np.arange(len(names))
    a.barh(y + 0.18, window_us, height=0.34, color="#CCCCCC", label="TAS gate window")
    colors = ["#0072B2"] * 4 + ["#C0392B"]
    a.barh(y - 0.18, frame_us, height=0.34, color=colors, label="one frame on the wire")
    for i, (f, w) in enumerate(zip(frame_us, window_us)):
        a.text(f + 4, i - 0.18, f"{f:g} µs", va="center", fontsize=9)
        a.text(w + 4, i + 0.18, f"{w} µs", va="center", fontsize=9, color="#555555")
    a.text(215, 2.82, "4 frames = 470 µs fit\nthe 500 µs window", fontsize=8.5, color="#0072B2", va="center")
    a.text(215, 3.82, "does not fit", fontsize=9.5, color="#C0392B", fontweight="bold", va="center")
    a.set_yticks(y)
    a.set_yticklabels(names, fontsize=9)
    a.invert_yaxis()
    a.set_xlabel("time at 100 Mbps (µs)")
    a.set_xlim(0, 560)
    a.set_title("Locked payloads are sized to their gate windows", fontsize=12, fontweight="bold", loc="left")
    a.legend(frameon=False, loc="lower right")

    labels = ["(1,0)", "(1,1)", "(2,1)", "(3,2)", "(4,3)", "(20,19)"]
    sizes = [360, 794, 948, 1536, 2124, 11532]
    bars = b.bar(labels, sizes, color=["#56B4E9"] * 3 + ["#E69F00"] * 3)
    for bar, v in zip(bars, sizes):
        b.text(bar.get_x() + bar.get_width() / 2, v * 1.06, f"{v:,}", ha="center", fontsize=9)
    b.axhline(600, color="#0072B2", lw=2)
    b.text(5.45, 520, "locked Orders = 600 B", color="#0072B2", ha="right", fontsize=9.5, fontweight="bold",
           bbox=dict(fc="white", ec="none", pad=1.5))
    b.axhline(1500, color="#C0392B", ls="--", lw=1.6)
    b.text(-0.45, 1650, "IPv4 MTU 1500 B (fragmentation above)", color="#C0392B", ha="left", fontsize=9.5,
           bbox=dict(fc="white", ec="none", pad=1.5))
    b.set_yscale("log")
    b.set_ylim(200, 25000)
    b.set_xlabel("VDA 5050 Order size by (graph nodes, edges)")
    b.set_ylabel("message size (bytes)")
    b.set_title("Realistic Orders exceed the MTU from 3 nodes", fontsize=12, fontweight="bold", loc="left")
    b.grid(axis="y", alpha=0.25)
    fig.suptitle("Frame sizes: what is locked and what that leaves out", fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    stamp(fig, None, "Sizes from docs/decisions.md (Wagner et al. 2026 Table I); wire times at 100 Mbps.")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, "F03_frame_sizes", ctx.args)


# --------------------------------------------------------------------------- F04
def fig_load_sweep(ctx) -> None:
    s = ctx.summary
    n = pick_n(s, ctx.args.n)
    phys = sorted(s["phy_rate_Mbps"].unique(), reverse=True)
    if ctx.args.phy:
        phys = [p for p in phys if p in ctx.args.phy]
    metric = ctx.args.metric
    fig, axes = plt.subplots(len(CLASSES), len(phys), figsize=(6.4 * len(phys) + 1, 2.7 * len(CLASSES) + 1),
                             sharex=True, squeeze=False)
    for j, phy in enumerate(phys):
        for i, cls in enumerate(CLASSES):
            ax = axes[i][j]
            d = s[(s["N_AMR"] == n) & (s["phy_rate_Mbps"] == phy) & (s["class"] == cls)]
            for c in CELLS:
                dc = d[d["cell"] == c].sort_values("lambda_tel_Mbps")
                if dc.empty:
                    continue
                kw = cell_kwargs(c)
                if len(dc) < 4:  # too few loads for a trend line: markers + faint dotted guide only
                    kw.update(ls=":", alpha=0.75)
                ax.plot(dc["lambda_tel_Mbps"], metric_values(dc, cls, metric), lw=2, ms=6, **kw)
            if metric in ("miss_A", "miss_B"):
                ax.axhline(1.0, color="#888888", ls=":", lw=1)
            for xv in (44.8, 95.0):
                ax.axvline(xv, color="#999999", ls="-.", lw=0.9, alpha=0.7)
            if i == 0:
                ax.set_title(f"{phy} Mbps PHY", fontsize=11.5, fontweight="bold", pad=20)
                ax.text(44.8, 1.02, "TAS cap", fontsize=7.5, color="#666666", ha="center",
                        transform=ax.get_xaxis_transform())
                ax.text(95.0, 1.02, "FIFO knee", fontsize=7.5, color="#666666", ha="center",
                        transform=ax.get_xaxis_transform())
            ax.set_ylabel(CLASS_LABEL[cls], fontsize=9.5)
            if metric in PERCENT_METRICS:
                ax.set_ylim(-3, 103)
            elif metric in ("p99", "p50"):
                ax.set_yscale("log")
            ax.grid(alpha=0.25)
    for ax in axes[-1]:
        ax.set_xlabel("Offered telemetry load (Mbps)")
    fig.legend(handles=cell_legend(), loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(f"Where the wired backbone saturates: {METRIC_LABEL[metric]} vs load, N = {n}",
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    n_loads = s[s["N_AMR"] == n]["lambda_tel_Mbps"].nunique()
    note = f"Only {n_loads} load points for N={n}: dotted guides are not a measured knee." if n_loads < 4 else ""
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    stamp(fig, s, note)
    save(fig, f"F04_load_sweep_N{n}_{metric}", ctx.args)


# --------------------------------------------------------------------------- F05
def fig_radio_scaling(ctx) -> None:
    s = ctx.summary
    lam = ctx.args.lam if ctx.args.lam is not None else float(sorted(s["lambda_tel_Mbps"].unique())[0])
    phys = sorted(s["phy_rate_Mbps"].unique(), reverse=True)
    if ctx.args.phy:
        phys = [p for p in phys if p in ctx.args.phy]
    classes = ["state", "orders", "dds"]
    metric = ctx.args.metric
    fig, axes = plt.subplots(len(classes), len(phys), figsize=(6.2 * len(phys) + 1, 2.9 * len(classes) + 1),
                             sharex=True, squeeze=False)
    for j, phy in enumerate(phys):
        for i, cls in enumerate(classes):
            ax = axes[i][j]
            d = s[(np.isclose(s["lambda_tel_Mbps"], lam)) & (s["phy_rate_Mbps"] == phy) & (s["class"] == cls)]
            for c in CELLS:
                dc = d[d["cell"] == c].sort_values("N_AMR")
                if dc.empty:
                    continue
                ax.plot(dc["N_AMR"], metric_values(dc, cls, metric), lw=2, ms=5, **cell_kwargs(c))
            if metric in ("miss_A", "miss_B"):
                ax.axhline(1.0, color="#888888", ls=":", lw=1)
            if i == 0:
                ax.set_title(f"{phy} Mbps PHY", fontsize=11.5, fontweight="bold")
            ax.set_ylabel(CLASS_LABEL[cls], fontsize=9.5)
            ax.set_xscale("log", base=2)
            ax.set_xticks(sorted(s["N_AMR"].unique()))
            ax.set_xticklabels(sorted(s["N_AMR"].unique()))
            if metric in PERCENT_METRICS:
                ax.set_ylim(-3, 103)
            elif metric in ("p99", "p50"):
                ax.set_yscale("log")
            ax.grid(alpha=0.25)
    for ax in axes[-1]:
        ax.set_xlabel("Fleet size N (AMRs)")
    fig.legend(handles=cell_legend(), loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(f"Radio scaling at telemetry {fmt_lambda(lam)} Mbps: {METRIC_LABEL[metric]} vs fleet size",
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    stamp(fig, s)
    save(fig, f"F05_radio_scaling_{metric}", ctx.args)


# --------------------------------------------------------------------------- F06
def fig_fingerprint(ctx) -> None:
    s = ctx.summary
    pts = parse_points(ctx.args.point, s)
    if not pts:
        raise RuntimeError("no operating point available")
    metric = ctx.args.metric if ctx.args.metric in PERCENT_METRICS else "miss_B"
    ncols = 2 if len(pts) > 1 else 1
    nrows = int(np.ceil(len(pts) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.4 * ncols + 2.0, 4.6 * nrows + 0.6), squeeze=False)
    im = None
    for k, ax in enumerate(axes.ravel()):
        if k >= len(pts):
            ax.axis("off")
            continue
        n, phy, lam = pts[k]
        d = s[(s["N_AMR"] == n) & (s["phy_rate_Mbps"] == phy) & np.isclose(s["lambda_tel_Mbps"], lam)]
        mat = np.full((len(CELLS), len(CLASSES)), np.nan)
        for ci, c in enumerate(CELLS):
            for ki, cls in enumerate(CLASSES):
                r = d[(d["cell"] == c) & (d["class"] == cls)]
                if not r.empty:
                    mat[ci, ki] = float(metric_values(r, cls, metric).iloc[0])
        im = ax.imshow(mat, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")
        for ci in range(mat.shape[0]):
            for ki in range(mat.shape[1]):
                v = mat[ci, ki]
                if np.isnan(v):
                    continue
                txt = "0" if v == 0 else (f"{v:.1f}" if v >= 0.1 else "<0.1")
                ax.text(ki, ci, txt, ha="center", va="center", fontsize=10.5,
                        color="white" if v > 60 else "black", fontweight="bold")
        ax.set_xticks(range(len(CLASSES)))
        ax.set_xticklabels([c.upper() if c == "dds" else c.capitalize() for c in CLASSES], fontsize=9.5)
        ax.set_yticks(range(len(CELLS)))
        ax.set_yticklabels([cell_label(c) for c in CELLS] if k % ncols == 0 else [""] * len(CELLS), fontsize=9)
        ax.set_title(point_title(n, phy, lam), fontsize=10.5, fontweight="bold")
    fig.suptitle("Treatment fingerprints: which architecture protects which class",
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 0.9, 0.95))
    cax = fig.add_axes([0.92, 0.2, 0.015, 0.6])
    fig.colorbar(im, cax=cax, label=METRIC_LABEL[metric])
    stamp(fig, s)
    save(fig, "F06_fingerprint", ctx.args)


# --------------------------------------------------------------------------- F07
def fig_bottleneck_map(ctx) -> None:
    b = ctx.bottleneck
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.2))
    ns = sorted(b["N_AMR"].unique())
    rows = sorted({(int(p), float(l)) for p, l in zip(b["phy_rate_Mbps"], b["lambda_tel_Mbps"])},
                  key=lambda t: (-t[0], t[1]))
    for ax, cls in zip(axes.ravel(), CLASSES):
        d = b[b["class"] == cls]
        for ri, (phy, lam) in enumerate(rows):
            for ni, n in enumerate(ns):
                r = d[(d["N_AMR"] == n) & (d["phy_rate_Mbps"] == phy) & np.isclose(d["lambda_tel_Mbps"], lam)]
                if r.empty:
                    ax.add_patch(Rectangle((ni, len(rows) - 1 - ri), 1, 1, fc="white", ec="#CCCCCC", lw=1.5, hatch="///"))
                    continue
                lab = str(r["dominant_bottleneck"].iloc[0])
                colour = BOTTLENECK_STYLE.get(lab, ("#FFFFFF", lab))[0]
                ax.add_patch(Rectangle((ni, len(rows) - 1 - ri), 1, 1, fc=colour, ec="white", lw=2))
                if "near_structural" in r and bool(r["near_structural"].iloc[0]):
                    ax.text(ni + 0.5, len(rows) - 1 - ri + 0.5, "≈struct.", ha="center", va="center", fontsize=7.5,
                            color="white" if _lum(colour) < 0.5 else "black")
        ax.set_xlim(0, len(ns))
        ax.set_ylim(0, len(rows))
        ax.set_xticks(np.arange(len(ns)) + 0.5)
        ax.set_xticklabels([f"N={n}" for n in ns])
        ax.set_yticks(np.arange(len(rows)) + 0.5)
        ax.set_yticklabels([f"{p} Mbps · {fmt_lambda(l)}" for p, l in reversed(rows)], fontsize=9)
        ax.set_title(CLASS_LABEL[cls], fontsize=11.5, fontweight="bold")
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    handles = [Patch(fc=c, ec="#777777", label=t) for k, (c, t) in BOTTLENECK_STYLE.items()
               if (b["dominant_bottleneck"] == k).any()]
    handles.append(Patch(fc="white", ec="#BBBBBB", hatch="///", label="not run"))
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Bottleneck migration: which intervention explains the misses, by condition",
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    stamp(fig, ctx.summary, "Rows: PHY rate · telemetry load (Mbps). 'Dominant' = which change helps more.")
    save(fig, "F07_bottleneck_map", ctx.args)


# --------------------------------------------------------------------------- F08
def fig_latency_ecdf(ctx) -> None:
    e = ctx.ecdf
    s = ctx.summary
    pts = parse_points(ctx.args.point, s)
    n, phy, lam = pts[0] if ctx.args.point else (pts[2] if len(pts) > 2 else pts[0])
    d = e[(e["N_AMR"] == n) & (e["phy_rate_Mbps"] == phy) & np.isclose(e["lambda_tel_Mbps"], lam)]
    if d.empty:
        raise RuntimeError("ECDF point not found")
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for ax, cls in zip(axes.ravel(), CLASSES):
        for c in CELLS:
            dc = d[(d["cell"] == c) & (d["class"] == cls)].sort_values("quantile_level")
            if dc.empty:
                continue
            ax.plot(np.maximum(dc["delay_ms"], 1e-3), dc["quantile_level"], drawstyle="steps-post",
                    lw=2, **{k: v for k, v in cell_kwargs(c).items() if k in ("color", "ls")})
        ax.axvline(NOMINAL_D[cls], color="black", ls=":", lw=1.3)
        ax.text(NOMINAL_D[cls], 0.04, f" D = {NOMINAL_D[cls]} ms", fontsize=8.5, rotation=90, va="bottom")
        ax.set_xscale("log")
        ax.set_ylim(0, 1.01)
        ax.set_title(CLASS_LABEL[cls], fontsize=11.5, fontweight="bold")
        ax.set_xlabel("end-to-end delay (ms)")
        ax.set_ylabel("fraction of delivered packets")
        ax.grid(alpha=0.25, which="both")
    fig.legend(handles=[Line2D([0], [0], label=cell_label(c), lw=2, color=cell_kwargs(c)["color"],
                               ls=cell_kwargs(c)["ls"]) for c in CELLS],
               loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(f"Delay distributions, {point_title(n, phy, lam)}", fontsize=13.5, fontweight="bold",
                 x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    stamp(fig, s, "Delivered packets only; losses are in F04/F06. 25-quantile summary.")
    save(fig, f"F08_latency_ecdf_N{n}_{phy}M_{fmt_lambda(lam)}", ctx.args)


# --------------------------------------------------------------------------- F09
def fig_domain_delay(ctx) -> None:
    dd = ctx.domain
    s = ctx.summary
    pts = parse_points(ctx.args.point, s)
    n, phy, lam = pts[0] if ctx.args.point else (pts[2] if len(pts) > 2 else pts[0])
    d = dd[(dd["N_AMR"] == n) & (dd["phy_rate_Mbps"] == phy) & np.isclose(dd["lambda_tel_Mbps"], lam)]
    if d.empty:
        raise RuntimeError("domain-delay point not found")
    g = d.groupby(["class", "cell", "domain"])["mean_ms"].mean().reset_index()
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for ax, cls in zip(axes.ravel(), CLASSES):
        gc = g[g["class"] == cls]
        bottom = np.zeros(len(CELLS))
        for dom in ("wireless", "wired_switch", "wire_serialization"):
            vals = np.array([gc[(gc["cell"] == c) & (gc["domain"] == dom)]["mean_ms"].sum() for c in CELLS])
            ax.bar([f"C{c}" for c in CELLS], vals, bottom=bottom, color=DOMAIN_COLOR[dom], label=DOMAIN_LABEL[dom])
            bottom += vals
        for xi, tot in enumerate(bottom):
            ax.text(xi, tot, f"{tot:.2f}", ha="center", va="bottom", fontsize=8.5)
        ax.set_title(CLASS_LABEL[cls], fontsize=11.5, fontweight="bold")
        ax.set_ylabel("mean delay of delivered packets (ms)")
        ax.grid(axis="y", alpha=0.25)
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(f"Where the time goes, {point_title(n, phy, lam)}", fontsize=13.5, fontweight="bold",
                 x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    stamp(fig, s, "Means over seeds, so a collapsed seed pulls them above the medians in F08 (see F10). Domains sum to the e2e mean.")
    save(fig, f"F09_domain_delay_N{n}_{phy}M_{fmt_lambda(lam)}", ctx.args)


# --------------------------------------------------------------------------- F10
def fig_seed_strip(ctx) -> None:
    r = ctx.reps
    s = ctx.summary
    pts = parse_points(ctx.args.point, s)
    n, phy, lam = pts[0] if ctx.args.point else (pts[2] if len(pts) > 2 else pts[0])
    d = r[(r["N_AMR"] == n) & (r["phy_rate_Mbps"] == phy) & np.isclose(r["lambda_tel_Mbps"], lam)]
    if d.empty:
        raise RuntimeError("replication point not found")
    classes = ["state", "orders", "dds"]
    rng = np.random.default_rng(7)
    fig, axes = plt.subplots(1, len(classes), figsize=(5.2 * len(classes) + 1, 5.6), squeeze=False)
    for ax, cls in zip(axes[0], classes):
        for xi, c in enumerate(CELLS):
            dc = d[(d["cell"] == c) & (d["class"] == cls)]
            if dc.empty:
                continue
            vals = dc[f"miss_B_{NOMINAL_D[cls]}ms"].to_numpy() * 100
            xs = xi + rng.uniform(-0.16, 0.16, len(vals))
            ax.scatter(xs, vals, s=34, color=cell_kwargs(c)["color"], alpha=0.8,
                       marker=cell_kwargs(c)["marker"], edgecolor="black", linewidth=0.4)
            ax.hlines(vals.mean(), xi - 0.28, xi + 0.28, color="black", lw=2)
            if vals.size and vals.max() - np.median(vals) > 15:
                k = int(np.argmax(vals))
                ax.annotate(f"seed {int(dc['rep'].iloc[k])}", (xs[k], vals[k]), textcoords="offset points",
                            xytext=(8, -2), fontsize=8.5, color="#C0392B")
        ax.set_xticks(range(len(CELLS)))
        ax.set_xticklabels([f"C{c}" for c in CELLS])
        ax.set_title(CLASS_LABEL[cls], fontsize=11.5, fontweight="bold")
        ax.set_ylabel("miss rate, Definition B (%)")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle(f"Seed-to-seed variability, {point_title(n, phy, lam)} (bar = mean)",
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    stamp(fig, s, "One dot = one seed. Show dots, not CI bars, while R is small.")
    save(fig, f"F10_seed_strip_N{n}_{phy}M_{fmt_lambda(lam)}", ctx.args)


# --------------------------------------------------------------------------- F11
def paired_effects(reps: pd.DataFrame) -> pd.DataFrame:
    """Per-condition paired contrasts (percentage points, positive = the change helps)."""
    rows = []
    keys = ["class", "N_AMR", "phy_rate_Mbps", "lambda_tel_Mbps"]
    for cls in CLASSES:
        d = reps[reps["class"] == cls].copy()
        d["v"] = d[f"miss_B_{NOMINAL_D[cls]}ms"] * 100.0
        wide = d.pivot_table(index=keys + ["rep"], columns="cell", values="v").dropna()
        if wide.empty or not set(CELLS) <= set(wide.columns):
            continue
        eff = pd.DataFrame({
            "radio": ((wide[1] - wide[2]) + (wide[3] - wide[4]) + (wide[5] - wide[6])) / 3,
            "fifo_tas": ((wide[1] - wide[5]) + (wide[2] - wide[6])) / 2,
            "fifo_prio": ((wide[1] - wide[3]) + (wide[2] - wide[4])) / 2,
        })
        for k, g in eff.groupby(level=keys):
            n = len(g)
            rec = dict(zip(keys, k))
            rec["n"] = n
            for col in eff.columns:
                rec[col] = g[col].mean()
                rec[col + "_ci"] = t975(n - 1) * g[col].std(ddof=1) / np.sqrt(n) if n >= 3 else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def fig_effect_sizes(ctx) -> None:
    s = ctx.summary
    eff = paired_effects(ctx.reps)
    if eff.empty:
        raise RuntimeError("no complete 6-cell paired seeds")
    structural = set()
    if ctx.bottleneck is not None:
        bb = ctx.bottleneck[ctx.bottleneck["dominant_bottleneck"] == "structural_schedule_wait"]
        structural = {(r["class"], int(r["N_AMR"]), int(r["phy_rate_Mbps"]), round(float(r["lambda_tel_Mbps"]), 3))
                      for _, r in bb.iterrows()}
    series = [("radio", "CSMA → Scheduled radio", "#D55E00"),
              ("fifo_tas", "FIFO → TAS", "#009E73"),
              ("fifo_prio", "FIFO → Priority", "#0072B2")]
    fig, axes = plt.subplots(2, 2, figsize=(16, 9.5))
    omitted = 0
    for ax, cls in zip(axes.ravel(), CLASSES):
        d = eff[eff["class"] == cls].copy()
        d["mag"] = d[[c for c, _, _ in series]].abs().max(axis=1)
        d = d[d["mag"] > 0.2]
        cap = max(2, ctx.args.max_conditions // 2)
        parts = []
        for _, g in d.groupby("phy_rate_Mbps"):  # keep both PHYs and both load extremes represented
            if len(g) > cap:
                omitted += len(g) - cap
                g = g.nlargest(cap, "mag")
            parts.append(g)
        d = pd.concat(parts) if parts else d
        d = d.sort_values(["phy_rate_Mbps", "N_AMR", "lambda_tel_Mbps"], ascending=[False, True, True])
        ax.set_title(CLASS_LABEL[cls], fontsize=11.5, fontweight="bold")
        if d.empty:
            ax.text(0.5, 0.5, "no effect above 0.2 pp", ha="center", transform=ax.transAxes)
            continue
        x = np.arange(len(d))
        wbar = 0.27
        for k, (col, label, colour) in enumerate(series):
            err = d[col + "_ci"].to_numpy(dtype=float)
            vals = d[col].to_numpy(dtype=float)
            bars = ax.bar(x + (k - 1) * wbar, vals, wbar, color=colour, label=label)
            fin = np.isfinite(err)
            if fin.any():  # draw a CI only for bars that have one (R >= 3)
                ax.errorbar((x + (k - 1) * wbar)[fin], vals[fin], yerr=err[fin], fmt="none", ecolor="black",
                            elinewidth=0.9, capsize=2)
            if col == "radio":
                for bar, r in zip(bars, d.itertuples()):
                    if (cls, int(r.N_AMR), int(r.phy_rate_Mbps), round(float(r.lambda_tel_Mbps), 3)) in structural:
                        bar.set_hatch("///")
                        bar.set_edgecolor("black")
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"N={int(r.N_AMR)}\n{int(r.phy_rate_Mbps)}M\n{fmt_lambda(r.lambda_tel_Mbps)}"
                            for r in d.itertuples()], fontsize=7.5, rotation=0)
        ax.set_ylabel("miss-rate reduction (pp)")
        ax.grid(axis="y", alpha=0.25)
    h = [Patch(fc=colour, label=label) for _, label, colour in series]
    l = [label for _, label, _ in series]
    h.append(Patch(fc="white", ec="black", hatch="///", label="radio contrast at a structural TDMA-wait point"))
    l.append("radio contrast at a structural TDMA-wait point")
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Paired treatment effects (positive = the change helps, negative = it hurts)",
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    note = "Per-seed contrasts pooled over cells (can differ by wired type); 95% CI only for R ≥ 3."
    if omitted:
        note += f" {omitted} smaller-effect conditions omitted."
    stamp(fig, s, note)
    save(fig, "F11_effect_sizes", ctx.args)
    _save_f11b_unpooled(ctx, structural)


def _save_f11b_unpooled(ctx, structural: set) -> None:
    """Companion figure: unpooled N=80, 12 Mbps radio contrasts stratified by wired architecture."""
    reps = ctx.reps
    if reps is None or reps.empty:
        return
    sub = reps[(reps["N_AMR"] == 80) & (reps["phy_rate_Mbps"] == 12)].copy()
    if sub.empty:
        return
    f11b_classes = ["orders", "dds", "state"]
    pairs = [("FIFO (C1 − C2)", 1, 2, WIRED_COLOR["FIFO"]),
             ("Priority (C3 − C4)", 3, 4, WIRED_COLOR["Priority"]),
             ("TAS (C5 − C6)", 5, 6, WIRED_COLOR["TAS"])]
    lams = sorted(sub["lambda_tel_Mbps"].unique())
    if not lams:
        return

    rows = []
    for cls in f11b_classes:
        dc = sub[sub["class"] == cls].copy()
        if dc.empty:
            continue
        dc["v"] = dc[f"miss_B_{NOMINAL_D[cls]}ms"] * 100.0
        for lam in lams:
            dl = dc[np.isclose(dc["lambda_tel_Mbps"], lam, atol=0.05)]
            piv = dl.pivot_table(index="rep", columns="cell", values="v")
            for pname, c_csma, c_sched, _col in pairs:
                if c_csma not in piv.columns or c_sched not in piv.columns:
                    continue
                both = piv[[c_csma, c_sched]].dropna()
                if both.empty:
                    continue
                diff = (both[c_csma] - both[c_sched]).to_numpy(dtype=float)
                n = len(diff)
                ci = t975(n - 1) * float(diff.std(ddof=1)) / np.sqrt(n) if n >= 3 else np.nan
                rows.append({"class": cls, "lam": float(lam), "pair": pname, "mean": float(diff.mean()), "ci": ci, "n": n})
    if not rows:
        return
    df_eff = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.2), sharey=False)
    for ax, cls in zip(axes, f11b_classes):
        dc = df_eff[df_eff["class"] == cls]
        present_lams = sorted(dc["lam"].unique())
        x = np.arange(len(present_lams))
        w = 0.25
        for k, (pname, _ca, _cb, colour) in enumerate(pairs):
            dp = dc[dc["pair"] == pname].set_index("lam")
            vals = np.array([dp.loc[l, "mean"] if l in dp.index else np.nan for l in present_lams], dtype=float)
            cis = np.array([dp.loc[l, "ci"] if l in dp.index else np.nan for l in present_lams], dtype=float)
            fin_v = np.isfinite(vals)
            if not fin_v.any():
                continue
            bars = ax.bar(x[fin_v] + (k - 1) * w, vals[fin_v], w, color=colour, label=pname)
            fin_ci = fin_v & np.isfinite(cis)
            if fin_ci.any():
                ax.errorbar(x[fin_ci] + (k - 1) * w, vals[fin_ci], yerr=cis[fin_ci],
                            fmt="none", ecolor="black", elinewidth=0.9, capsize=2.5)
            for bar, lval in zip(bars, np.array(present_lams)[fin_v]):
                if (cls, 80, 12, round(float(lval), 3)) in structural:
                    bar.set_hatch("///")
                    bar.set_edgecolor("black")
        ax.axhline(0.0, color="black", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{fmt_lambda(l)} Mbps" for l in present_lams], fontsize=9)
        ax.set_title(CLASS_LABEL[cls], fontsize=11, fontweight="bold")
        ax.set_ylabel("CSMA − Scheduled miss reduction (pp)")
        ax.grid(axis="y", alpha=0.25)

    handles = [Patch(fc=col, label=lbl) for lbl, _, _, col in pairs]
    handles.append(Patch(fc="white", ec="black", hatch="///", label="structural TDMA-wait point"))
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("N = 80, 12 Mbps: unpooled wireless contrasts by wired architecture",
                 fontsize=13, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    stamp(fig, ctx.summary, "Positive = Scheduled lowers miss rate vs CSMA (pp); 95% Student-t CI for R >= 3.")
    save(fig, "F11b_effect_sizes_unpooled_N80_12M", ctx.args)


# --------------------------------------------------------------------------- F12
def fig_runtime(ctx) -> None:
    base, opt = ctx.manifest_base, ctx.manifest_opt
    if base is None and opt is None:
        raise RuntimeError("no manifest supplied")

    def prep(m: pd.DataFrame) -> pd.DataFrame:
        m = m[m["exit_code"] == 0].copy()
        m["lam"] = m["telInterval"].map(TEL_MBPS)
        return m

    frames = {k: prep(v) for k, v in (("baseline", base), ("optimized", opt)) if v is not None}
    ref = next(iter(frames.values()))
    conds = sorted({(int(a), t) for a, t in zip(ref["nAmr"], ref["telInterval"])},
                   key=lambda x: (TEL_MBPS.get(x[1], 0), x[0]))
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw=dict(width_ratios=[1.5, 1]))
    xs = np.arange(len(conds))
    width = 0.38 if len(frames) == 2 else 0.6
    means = {}
    for k, (name, m) in enumerate(frames.items()):
        mu = np.array([m[(m["nAmr"] == n) & (m["telInterval"] == t)]["wall_seconds"].mean() for n, t in conds])
        means[name] = mu
        off = (k - (len(frames) - 1) / 2) * width
        a.bar(xs + off, mu / 60, width, label=name, color="#B0B0B0" if name == "baseline" else "#0072B2")
    a.set_xticks(xs)
    a.set_xticklabels([f"N={n}\n{fmt_lambda(TEL_MBPS.get(t, np.nan))} Mbps" for n, t in conds], fontsize=9)
    a.set_ylabel("mean wall time per 60 s run (minutes)")
    a.set_title("Cost of one run grows with fleet size and telemetry load", fontsize=12, fontweight="bold", loc="left")
    a.legend(frameon=False)
    a.grid(axis="y", alpha=0.25)
    if len(frames) == 2:
        sp = means["baseline"] / means["optimized"]
        b.bar(xs, sp, color="#009E73")
        for xi, v in zip(xs, sp):
            b.text(xi, v + 0.04, f"{v:.2f}×", ha="center", fontsize=9, zorder=5,
                   bbox=dict(fc="white", ec="none", pad=0.8))
        tot_b = frames["baseline"]["wall_seconds"].sum()
        tot_o = frames["optimized"]["wall_seconds"].sum()
        b.axhline(tot_b / tot_o, color="black", ls="--", lw=1.2)
        b.text(0.02, 0.97, f"overall {tot_b / tot_o:.2f}× (ratio of total run time)", transform=b.transAxes,
               ha="left", va="top", fontsize=10)
        b.set_xticks(xs)
        b.set_xticklabels([f"N={n}\n{fmt_lambda(TEL_MBPS.get(t, np.nan))}" for n, t in conds], fontsize=8)
        b.set_ylim(0, max(sp) * 1.3)
        b.set_ylabel("speedup (baseline / optimized)")
        b.set_title("Bit-identical results, 2.3× faster", fontsize=12, fontweight="bold", loc="left")
        b.grid(axis="y", alpha=0.25)
        w = max(1, ctx.args.workers)
        fig.text(0.995, 0.01,
                 f"Σ per-run time {tot_b / 3600:.1f} → {tot_o / 3600:.1f} core-hours over {len(frames['optimized'])} runs "
                 f"(≈ {tot_b / 3600 / w:.1f} → {tot_o / 3600 / w:.1f} h wall on {w} workers)",
                 ha="right", fontsize=9, color="#444444")
    else:
        b.axis("off")
    fig.suptitle("Optimization: measured wall-clock under 4 parallel workers", fontsize=13.5, fontweight="bold",
                 x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    save(fig, "F12_runtime_speedup", ctx.args)


# --------------------------------------------------------------------------- F13
def fig_surface3d(ctx) -> None:
    s = ctx.summary
    cls = ctx.args.cls3d
    phy = ctx.args.phy3d if ctx.args.phy3d is not None else int(min(s["phy_rate_Mbps"]))
    metric = ctx.args.metric if ctx.args.metric in PERCENT_METRICS else "miss_B"
    pair = ctx.args.surface_cells
    d = s[(s["class"] == cls) & (s["phy_rate_Mbps"] == phy)]
    ns = sorted(d["N_AMR"].unique())
    lams = sorted(d["lambda_tel_Mbps"].unique())
    if len(ns) < 2 or len(lams) < 2:
        raise RuntimeError("need >= 2 values of N and of load")
    zmax = max(5.0, float(np.nanmax([metric_values(d[d["cell"] == c], cls, metric).max() for c in pair])) * 1.05)
    fig = plt.figure(figsize=(14, 6.4))
    drew_bars = False
    for k, c in enumerate(pair):
        ax = fig.add_subplot(1, len(pair), k + 1, projection="3d")
        dc = d[d["cell"] == c]
        z = np.full((len(ns), len(lams)), np.nan)
        for i, n in enumerate(ns):
            for j, l in enumerate(lams):
                r = dc[(dc["N_AMR"] == n) & np.isclose(dc["lambda_tel_Mbps"], l)]
                if not r.empty:
                    z[i, j] = float(metric_values(r, cls, metric).iloc[0])
        finite = np.isfinite(z)
        if getattr(ctx.args, "require_complete", False) and not finite.all():
            raise RuntimeError(f"F13: incomplete surface grid for cell={c}, class={cls}, phy={phy}")
        if finite.all() and len(ns) >= 3 and len(lams) >= 3:
            nx = np.log2(np.asarray(ns, dtype=float))
            ly = np.asarray(lams, dtype=float)
            X, Y = np.meshgrid(nx, ly, indexing="ij")
            ax.plot_surface(X, Y, z, cmap="YlOrRd", vmin=0, vmax=zmax, edgecolor="#555555",
                            linewidth=0.4, alpha=0.95)
            ax.set_xticks(nx)
            ax.set_xticklabels([str(int(n)) for n in ns])
            ax.set_yticks(ly)
            ax.set_yticklabels([fmt_lambda(x) for x in lams], fontsize=8)
            ax.set_xlabel("fleet size N (log2 scale)", labelpad=8)
        else:  # sparse or incomplete grid: bars only where a simulation exists
            drew_bars = True
            X, Y = np.meshgrid(np.arange(len(ns)), np.arange(len(lams)), indexing="ij")
            zf = z[finite]
            ax.bar3d(X[finite] - 0.25, Y[finite] - 0.25, np.zeros(zf.size), 0.5, 0.5, zf,
                     color=plt.cm.YlOrRd(np.clip(zf / zmax, 0, 1)), shade=True)
            ax.set_xticks(range(len(ns)))
            ax.set_xticklabels(ns)
            ax.set_yticks(range(len(lams)))
            ax.set_yticklabels([fmt_lambda(x) for x in lams], fontsize=8)
            ax.set_xlabel("fleet size N", labelpad=8)
        ax.set_ylabel("telemetry load (Mbps)", labelpad=10)
        ax.set_zlabel(METRIC_LABEL[metric].split(",")[0].replace("Deadline-miss rate", "miss rate") + " (%)" if metric in PERCENT_METRICS else METRIC_LABEL[metric], labelpad=8)
        ax.set_zlim(0, zmax)
        ax.view_init(elev=26, azim=-125)
        ax.set_title(cell_label(c), fontsize=11.5, fontweight="bold", color=WIRED_COLOR[CELLS[c][1]])
    fig.suptitle(f"{CLASS_LABEL[cls]} at {phy} Mbps: same wired switch, different radio" + (" (bars only where simulated)" if drew_bars else ""),
                 fontsize=13.5, fontweight="bold", x=0.01, ha="left")
    stamp(fig, s)
    save(fig, f"F13_surface3d_{cls}_{phy}M", ctx.args)


# --------------------------------------------------------------------------- F14..F16 (interim 20h extras)
def _extra_dir(ctx) -> Path:
    return Path(getattr(ctx.args, "extra_dir", "report/interim_20h/deliverable/tables/extra"))


def fig_collapse_and_diag(ctx) -> None:
    ed = _extra_dir(ctx)
    per_seed = read_csv(ed, "collapse_b_per_seed.csv")
    csum = read_csv(ed, "collapse_b_summary.csv")
    if per_seed is None or per_seed.empty or csum is None or csum.empty:
        raise RuntimeError("missing or empty collapse_b_per_seed.csv / collapse_b_summary.csv")
    diag_sum = read_csv(ed, "diag_rep3_summary.csv")
    diag_ts = read_csv(ed, "diag_rep3_timeseries.csv")
    has_diag = diag_ts is not None and not diag_ts.empty

    r50 = csum[np.isclose(csum["threshold_tau"], 0.50)]
    if not r50.empty:
        r0 = r50.iloc[0]
        cp_note = (
            f"tau=50%: {int(r0['k_exceed'])}/{int(r0['n_seeds'])} = {100*r0['p_hat']:.1f}% "
            f"(95% CP CI [{100*r0['ci95_lo']:.1f}%, {100*r0['ci95_hi']:.1f}%])"
        )
    else:
        cp_note = f"n={len(per_seed)} seeds"

    if has_diag:
        fig, axes = plt.subplots(2, 2, figsize=(15.5, 9.5))
        ax_seed, ax_tau, ax_q, ax_mac = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]
    else:
        fig, axes = plt.subplots(1, 2, figsize=(15.0, 5.2))
        ax_seed, ax_tau = axes[0], axes[1]
        ax_q = ax_mac = None

    reg_color = {"collapsed": "#D55E00", "intermediate": "#E69F00", "normal": "#0072B2"}
    per_seed = per_seed.sort_values("rep")
    for reg, lbl in (("normal", "normal (<10%)"), ("intermediate", "intermediate [10,50%)"), ("collapsed", "collapsed (>=50%)")):
        sub = per_seed[per_seed["regime"] == reg]
        if not sub.empty:
            ax_seed.scatter(sub["rep"], sub["state_miss_B_50ms"] * 100.0, c=reg_color[reg], s=42, zorder=3, label=f"State: {lbl}")
    ax_seed.plot(per_seed["rep"], per_seed["orders_miss_B_50ms"] * 100.0, color="#666666", lw=1.0, ls=":", marker="x", ms=4, label="Orders miss_B (50 ms)")
    ax_seed.axhline(50.0, color="#D55E00", ls="--", lw=1.0, alpha=0.8)
    ax_seed.axhline(10.0, color="#E69F00", ls=":", lw=1.0, alpha=0.8)
    ax_seed.set_ylim(-3, 105)
    ax_seed.set_xlabel("replication index (rep)")
    ax_seed.set_ylabel("miss_B (%)")
    ax_seed.set_title(f"Cell 1 (N=80, 12M, 2000us) per-seed collapse\n{cp_note}", fontsize=11, fontweight="bold")
    ax_seed.grid(alpha=0.25)
    ax_seed.legend(fontsize=8, loc="upper right", framealpha=0.9)

    csum = csum.sort_values("threshold_tau")
    taus = csum["threshold_tau"] * 100.0
    phat = csum["p_hat"] * 100.0
    lo_err = np.maximum(0.0, (csum["p_hat"] - csum["ci95_lo"]) * 100.0)
    hi_err = np.maximum(0.0, (csum["ci95_hi"] - csum["p_hat"]) * 100.0)
    ax_tau.errorbar(taus, phat, yerr=[lo_err, hi_err], fmt="o-", color="#D55E00", capsize=4, lw=1.8)
    ax_tau.set_ylim(-3, 105)
    ax_tau.set_xlabel("State miss_B threshold tau (%)")
    ax_tau.set_ylabel("collapsed fraction (%)")
    ax_tau.set_title("Threshold sensitivity with Clopper–Pearson 95% CI", fontsize=11, fontweight="bold")
    ax_tau.grid(alpha=0.25)
    if not has_diag:
        ax_tau.text(0.5, 0.88, "diag_rep3 (Cells 1,3,5 rep=3 MAC/queue traces) pending Block B",
                    ha="center", transform=ax_tau.transAxes, fontsize=8.5, color="#555555")

    if has_diag and ax_q is not None and ax_mac is not None:
        for cell in sorted(diag_ts["cell"].unique()):
            dc = diag_ts[diag_ts["cell"] == cell].sort_values("bin_s")
            kw = cell_kwargs(int(cell))
            ax_q.plot(dc["bin_s"], dc["ap_q_mean"], color=kw["color"], ls=kw["ls"], lw=1.6, label=f"{cell_label(int(cell))} (AP mean)")
            ax_q.plot(dc["bin_s"], dc["ap_q_max"], color=kw["color"], ls=":", lw=1.0, alpha=0.55)
        ax_q.set_xlabel("simulation time bin (1 s, rep = 3)")
        ax_q.set_ylabel("AP pendingQueue length (frames)")
        ax_q.set_title("rep = 3 diagnostic: AP MAC pendingQueue trace (solid=mean, dotted=max)", fontsize=10.5, fontweight="bold")
        ax_q.grid(alpha=0.25)
        ax_q.legend(fontsize=8)

        if diag_sum is not None and not diag_sum.empty:
            metrics = [("ap_drop_retry", "AP retry drop"),
                       ("amr_drop_retry", "AMR retry drop"),
                       ("ap_drop_queue", "AP queue drop"),
                       ("sw_drop_queue", "Switch queue drop")]
            ds = diag_sum.sort_values("cell")
            x = np.arange(len(metrics))
            w = 0.25
            for idx_c, (_, row) in enumerate(ds.iterrows()):
                c = int(row["cell"])
                vals = [max(0.0, float(row[m])) for m, _ in metrics]
                bars = ax_mac.bar(x + (idx_c - 1) * w, vals, w, color=cell_kwargs(c)["color"], label=cell_label(c))
                for bar, v in zip(bars, vals):
                    if v > 0:
                        ax_mac.text(bar.get_x() + bar.get_width() / 2, v, f"{int(round(v))}", ha="center", va="bottom", fontsize=7.5)
            ax_mac.set_xticks(x)
            ax_mac.set_xticklabels([lbl for _, lbl in metrics], fontsize=9)
            ax_mac.set_ylabel("packet drop count (total in run)")
            ax_mac.set_title("rep = 3 MAC & switch drop breakdown across CSMA cells", fontsize=10.5, fontweight="bold")
            ax_mac.grid(axis="y", alpha=0.25)
            ax_mac.legend(fontsize=8)

    fig.suptitle("Cell 1 collapse incidence & rep = 3 CSMA diagnostic trace (N = 80, 12 Mbps, 2000 us)",
                 fontsize=13, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    stamp(fig, ctx.summary, "Clopper–Pearson 95% exact binomial CIs.")
    save(fig, "F14_collapse_and_diag", ctx.args)


def fig_conformance_map(ctx) -> None:
    ed = _extra_dir(ctx)
    conf = read_csv(ed, "conformance_map.csv")
    if conf is None or conf.empty:
        raise RuntimeError("missing or empty conformance_map.csv")
    pools = list(conf["pool"].unique())
    dir_name = Path(ctx.args.lookup_dir).name
    chosen_pool = dir_name if dir_name in pools else ("core_r3" if "core_r3" in pools else pools[0])
    d = conf[conf["pool"] == chosen_pool].copy()
    wanted_loads = _parse_loads(getattr(ctx.args, "loads", ""))
    if wanted_loads:
        d = _filter_by_loads(d, wanted_loads)
    if d.empty:
        raise RuntimeError(f"no conformance rows for pool={chosen_pool}")

    from matplotlib.colors import ListedColormap
    state_code = {"conforms": 0, "unresolved": 1, "violates": 2}
    cmap = ListedColormap(["#009E73", "#E69F00", "#D55E00"])
    cmap.set_bad("#F0F0F0")

    phys = sorted(d["phy_rate_Mbps"].unique(), reverse=True)
    nl_pairs = sorted({(int(r["N_AMR"]), float(r["lambda_tel_Mbps"])) for _, r in d.iterrows()})
    col_pairs = [(c, cls) for c in sorted(CELLS) for cls in CLASSES]
    short_cls = {"dds": "D", "state": "S", "orders": "O", "telemetry": "T"}

    fig, axes = plt.subplots(1, len(phys), figsize=(max(12, 7.5 * len(phys)), max(5.5, 0.36 * len(nl_pairs) + 2.2)), sharey=True)
    if len(phys) == 1:
        axes = [axes]
    for ax, phy in zip(axes, phys):
        dp = d[d["phy_rate_Mbps"] == phy]
        mat = np.full((len(nl_pairs), len(col_pairs)), np.nan)
        lookup = {(int(r["N_AMR"]), round(float(r["lambda_tel_Mbps"]), 3), int(r["cell"]), str(r["class"])): state_code.get(str(r["state"]), np.nan)
                  for _, r in dp.iterrows()}
        for i, (n_amr, lam) in enumerate(nl_pairs):
            for j, (c, cls) in enumerate(col_pairs):
                val = lookup.get((n_amr, round(lam, 3), c, cls), np.nan)
                mat[i, j] = val
        ax.imshow(np.ma.masked_invalid(mat), cmap=cmap, vmin=0, vmax=2, aspect="auto")
        for xdiv in range(4, len(col_pairs), 4):
            ax.axvline(xdiv - 0.5, color="white", lw=2.0)
        for ydiv in range(len(nl_pairs) - 1):
            if nl_pairs[ydiv][0] != nl_pairs[ydiv + 1][0]:
                ax.axhline(ydiv + 0.5, color="white", lw=1.5)
        ax.set_xticks(range(len(col_pairs)))
        ax.set_xticklabels([short_cls[cls] for _, cls in col_pairs], fontsize=7.5)
        for c_idx, c in enumerate(sorted(CELLS)):
            ax.text(c_idx * 4 + 1.5, -0.85, f"C{c}", ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color=WIRED_COLOR[CELLS[c][1]])
        ax.set_yticks(range(len(nl_pairs)))
        ax.set_yticklabels([f"N={n}, {fmt_lambda(l)}" for n, l in nl_pairs], fontsize=8)
        ax.set_title(f"{int(phy)} Mbps PHY", fontsize=11.5, fontweight="bold", pad=22)

    handles = [
        Patch(fc="#009E73", label="conforms (UCB95 <= 1%, prereg G8a)"),
        Patch(fc="#E69F00", label="unresolved (95% CI straddles 1%)"),
        Patch(fc="#D55E00", label="violates (LCB95 > 1%, addition beyond prereg)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    n_reps_txt = f"R={int(d['n_reps'].min())}" if int(d['n_reps'].min()) == int(d['n_reps'].max()) else f"R={int(d['n_reps'].min())}-{int(d['n_reps'].max())}"
    fig.suptitle(f"3-state operational conformance map ({chosen_pool}, {n_reps_txt}; D/S/O/T per Cell)",
                 fontsize=13, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    stamp(fig, ctx.summary, "0-miss cells use pooled Wilson UCB (ignores within-seed burst correlation).")
    save(fig, "F15_conformance_map", ctx.args)


def fig_g8b_loo(ctx) -> None:
    ed = _extra_dir(ctx)
    loo = read_csv(ed, "g8b_loo_error.csv")
    if loo is None or loo.empty:
        raise RuntimeError("missing or empty g8b_loo_error.csv")

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8))
    groups = []
    for (pool, mode), g in loo.groupby(["pool", "mode"], sort=True):
        groups.append((f"{pool}\n{mode}", g))

    x_base = np.arange(len(CLASSES))
    offsets = np.linspace(-0.26, 0.26, max(1, len(groups))) if len(groups) > 1 else [0.0]
    w = 0.22 if len(groups) > 1 else 0.4
    mode_colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7"]

    for idx_g, ((g_label, gdf), col) in enumerate(zip(groups, mode_colors)):
        pos = x_base + offsets[idx_g]
        w1_data = [gdf[gdf["class"] == cls]["w1_ms"].dropna().to_numpy(dtype=float) for cls in CLASSES]
        mb_data = [(gdf[gdf["class"] == cls]["abs_err_miss_B_nom"].dropna() * 100.0).to_numpy(dtype=float) for cls in CLASSES]
        for ax, data in ((axes[0], w1_data), (axes[1], mb_data)):
            valid_pos = [p for p, arr in zip(pos, data) if len(arr) > 0]
            valid_arr = [arr for arr in data if len(arr) > 0]
            if valid_arr:
                bp = ax.boxplot(valid_arr, positions=valid_pos, widths=w * 0.85, patch_artist=True,
                                showfliers=False, medianprops=dict(color="black", lw=1.4))
                for box in bp["boxes"]:
                    box.set_facecolor(col)
                    box.set_alpha(0.75)

    from matplotlib.lines import Line2D

    fin_w1 = loo["boot_r3_rmse_w1_ms"].dropna()
    w1_med = float(fin_w1.median()) if not fin_w1.empty else float("nan")
    if np.isfinite(w1_med):
        axes[0].axhline(w1_med, color="#444444", ls="--", lw=1.2)
    fin_mb = loo["boot_r3_rmse_miss_B"].dropna()
    mb_med = float(fin_mb.median()) * 100.0 if not fin_mb.empty else float("nan")
    if np.isfinite(mb_med):
        axes[1].axhline(mb_med, color="#444444", ls="--", lw=1.2)

    if loo["w1_ms"].max() > 15.0:
        axes[0].set_yscale("symlog", linthresh=1.0)
    axes[0].set_ylabel("Wasserstein-1 ECDF error (ms)")
    w1_sub = f" (noise median {w1_med:.2f} ms)" if np.isfinite(w1_med) else ""
    axes[0].set_title(f"Leave-One-Out ECDF error (1D W1){w1_sub}", fontsize=11, fontweight="bold")
    axes[1].set_ylabel("|pred miss_B - emp miss_B| (pp)")
    mb_sub = f" (noise median {mb_med:.2f} pp)" if np.isfinite(mb_med) else ""
    axes[1].set_title(f"Leave-One-Out nominal miss_B error{mb_sub}", fontsize=11, fontweight="bold")
    for ax in axes:
        ax.set_xticks(x_base)
        ax.set_xticklabels([cls.upper() for cls in CLASSES], fontsize=9.5)
        ax.grid(axis="y", alpha=0.25)
        y0, y1 = ax.get_ylim()
        ax.set_ylim(y0, y1 * (1.25 if ax is axes[0] else 1.10))

    handles = [Patch(fc=col, alpha=0.75, label=lbl.replace("\n", " ")) for (lbl, _), col in zip(groups, mode_colors)]
    if np.isfinite(w1_med) or np.isfinite(mb_med):
        handles.append(Line2D([0], [0], color="#444444", ls="--", lw=1.3, label="R=3 bootstrap median noise floor"))
    fig.legend(handles=handles, loc="lower center", ncol=min(4, len(handles)), frameon=False, bbox_to_anchor=(0.5, -0.01))

    fig.suptitle("G8b LOO PCHIP error vs R=3 noise floor",
                 fontsize=13, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    stamp(fig, ctx.summary, "Boxplots omit extreme fliers (1.5 IQR); PCHIP matches export_lookup.")
    save(fig, "F16_g8b_interpolation_loo", ctx.args)


# --------------------------------------------------------------------------- driver
class Ctx:
    pass


FIGURES = {
    "F01": ("design_overview", fig_design_overview, ()),
    "F02": ("capacity", fig_capacity, ()),
    "F03": ("frame_sizes", fig_frame_sizes, ()),
    "F04": ("load_sweep", fig_load_sweep, ("summary",)),
    "F05": ("radio_scaling", fig_radio_scaling, ("summary",)),
    "F06": ("fingerprint", fig_fingerprint, ("summary",)),
    "F07": ("bottleneck_map", fig_bottleneck_map, ("bottleneck",)),
    "F08": ("latency_ecdf", fig_latency_ecdf, ("summary", "ecdf")),
    "F09": ("domain_delay", fig_domain_delay, ("summary", "domain")),
    "F10": ("seed_strip", fig_seed_strip, ("summary", "reps")),
    "F11": ("effect_sizes", fig_effect_sizes, ("summary", "reps")),
    "F12": ("runtime_speedup", fig_runtime, ()),
    "F13": ("surface3d", fig_surface3d, ("summary",)),
    "F14": ("collapse_and_diag", fig_collapse_and_diag, ()),
    "F15": ("conformance_map", fig_conformance_map, ()),
    "F16": ("g8b_interpolation_loo", fig_g8b_loo, ()),
}


def _parse_loads(loads_str: str) -> List[float]:
    if not loads_str or not str(loads_str).strip():
        return []
    return [float(tok.strip()) for tok in str(loads_str).split(",") if tok.strip()]


def _filter_by_loads(df: Optional[pd.DataFrame], wanted_loads: Sequence[float]) -> Optional[pd.DataFrame]:
    if df is None or df.empty or not wanted_loads or "lambda_tel_Mbps" not in df.columns:
        return df
    vals = df["lambda_tel_Mbps"].to_numpy(dtype=float)
    mask = np.zeros(len(df), dtype=bool)
    for lval in wanted_loads:
        mask |= np.isclose(vals, float(lval), atol=0.15)
    return df[mask].copy()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lookup-dir", default="evidence/05_dry_run_opt/lookup",
                   help="directory with the exporter CSVs")
    p.add_argument("--out", default="figures")
    p.add_argument("--extra-dir", default="report/interim_20h/deliverable/tables/extra",
                   help="directory containing Stage-2+ extra CSVs (F14-F16)")
    p.add_argument("--manifest-base", default=None, help="baseline launcher manifest.csv (F12)")
    p.add_argument("--manifest-opt", default=None, help="optimized launcher manifest.csv (F12)")
    p.add_argument("--only", nargs="*", default=None, help="figure ids, e.g. F04 F08")
    p.add_argument("--format", nargs="+", default=["png"], choices=["png", "pdf", "svg"])
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--max-conditions", type=int, default=18, help="F11: max conditions per class (split over PHYs)")
    p.add_argument("--workers", type=int, default=4, help="parallel workers used by the campaign (F12 label)")
    p.add_argument("--metric", default="miss_B", choices=list(METRIC_LABEL))
    p.add_argument("--n", type=int, default=None, help="fleet size for F04 (default: best covered)")
    p.add_argument("--phy", type=int, nargs="*", default=None, help="PHY rates to show in F04/F05")
    p.add_argument("--lam", type=float, default=None, help="telemetry load for F05 (default: lowest)")
    p.add_argument("--point", action="append", default=None, metavar="N,PHY,LOAD",
                   help="operating point for F06/F08/F09/F10 (repeatable for F06)")
    p.add_argument("--class3d", dest="cls3d", default="orders", choices=CLASSES)
    p.add_argument("--phy3d", type=int, default=None)
    p.add_argument("--surface-cells", type=int, nargs=2, default=[1, 2], metavar=("A", "B"),
                   help="two cells compared in F13 (default 1 2: CSMA vs Scheduled, FIFO)")
    p.add_argument("--loads", default="", help="comma-separated telemetry loads (Mbps) to keep")
    p.add_argument("--require-complete", action="store_true",
                   help="fail with RuntimeError if the filtered grid has holes or non-uniform n_reps")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = Ctx()
    ctx.args = args
    d = Path(args.lookup_dir)
    wanted_loads = _parse_loads(args.loads)
    ctx.summary = _filter_by_loads(read_csv(d, "lookup_summary.csv"), wanted_loads)
    ctx.ecdf = _filter_by_loads(read_csv(d, "lookup_ecdf.csv"), wanted_loads)
    ctx.reps = _filter_by_loads(read_csv(d, "lookup_replications.csv"), wanted_loads)
    ctx.domain = _filter_by_loads(read_csv(d, "lookup_domain_delay.csv"), wanted_loads)
    ctx.bottleneck = _filter_by_loads(read_csv(d, "bottleneck_migration.csv"), wanted_loads)
    ctx.manifest_base = pd.read_csv(args.manifest_base) if args.manifest_base else None
    ctx.manifest_opt = pd.read_csv(args.manifest_opt) if args.manifest_opt else None

    if args.require_complete:
        assert_complete_grid(ctx.summary, wanted_loads)

    plt.rcParams.update({"font.size": 10.5, "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": "white"})
    wanted = [x.upper() for x in args.only] if args.only else list(FIGURES)
    done, skipped = [], []
    for fid in wanted:
        if fid not in FIGURES:
            print(f"unknown figure {fid}", file=sys.stderr)
            continue
        name, fn, needs = FIGURES[fid]
        missing = [k for k in needs if getattr(ctx, k) is None]
        if fid == "F12" and ctx.manifest_base is None and ctx.manifest_opt is None:
            missing = ["manifest"]
        if missing:
            skipped.append((fid, f"missing input: {', '.join(missing)}"))
            continue
        print(f"{fid} {name}")
        try:
            fn(ctx)
            done.append(fid)
        except Exception as exc:  # keep going: one bad figure must not block the rest
            skipped.append((fid, f"{type(exc).__name__}: {exc}"))
            if args.only:
                traceback.print_exc()
    print(f"\nwritten: {', '.join(done) or '-'}")
    for fid, why in skipped:
        print(f"skipped {fid}: {why}")
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
