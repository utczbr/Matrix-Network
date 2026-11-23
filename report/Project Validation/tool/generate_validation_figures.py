#!/usr/bin/env python3
"""Generate publication-grade vector PDF figures for the Stage P3 Validation Report.

Reads directly from report/Project Validation/tables/ and evidence/ manifests,
enforces two strictly orthogonal colorblind-safe Okabe-Ito/Tol palettes (one for
wired switch/MAC disciplines, one for 3-domain delay attribution), removes
dual y-axes and redundant embedded suptitles, and exports vector PDFs to
report/Project Validation/images/pdf/.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

TOOL_DIR = Path(__file__).resolve().parent
VAL_DIR = TOOL_DIR.parent
REPO_DIR = VAL_DIR.parent.parent
IMG_DIR = VAL_DIR / "images"
PDF_DIR = IMG_DIR / "pdf"
TBL_DIR = VAL_DIR / "tables"
EXTRAS = TBL_DIR / "extra"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "STIXGeneral", "Times New Roman"],
    "mathtext.fontset": "stix",
    "font.size": 9.5,
    "axes.titlesize": 10.2,
    "axes.titleweight": "bold",
    "axes.labelsize": 9.4,
    "xtick.labelsize": 8.6,
    "ytick.labelsize": 8.6,
    "legend.fontsize": 7.8,
    "axes.grid": True,
    "grid.alpha": 0.28,
    "grid.linestyle": "--",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

LOADS_8 = [22.4, 45.0, 60.0, 74.7, 85.0, 95.0, 110.0, 149.3]
TEL_MBPS = {
    "2000us": 22.4, "996us": 45.0, "747us": 60.0, "600us": 74.7,
    "527us": 85.0, "472us": 95.0, "407us": 110.0, "300us": 149.3,
}
CELLS = {
    1: ("CSMA", "FIFO"), 2: ("Scheduled", "FIFO"),
    3: ("CSMA", "Priority"), 4: ("Scheduled", "Priority"),
    5: ("CSMA", "TAS"), 6: ("Scheduled", "TAS"),
}

# Strictly orthogonal palettes:
# 1) Wired switch / cell discipline palette (Okabe-Ito)
WIRED_COLOR = {"FIFO": "#D55E00", "Priority": "#0072B2", "TAS": "#009E73"}
# 2) Domain delay palette (never overlaps with WIRED_COLOR or cell colors)
DOMAIN_COLOR = {
    "wired_switch": "#332288",
    "wireless": "#CC79A7",
    "wire_serialization": "#7F7F7F",
}
NOMINAL_D = {"dds": 5, "state": 50, "orders": 50, "telemetry": 100}


def _pick_pt(df: pd.DataFrame, **cond) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for k, v in cond.items():
        if isinstance(v, float):
            mask &= np.isclose(df[k], v, atol=0.15)
        else:
            mask &= (df[k] == v)
    return df[mask]


def _save_pdf(fig: plt.Figure, filename: str) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PDF_DIR / filename, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_fig_vda_gcl(apw: pd.DataFrame) -> None:
    """Analytical 100 Mbps wire serialization vs. per-class 802.1Qbv gate windows."""
    apw_idx = apw.set_index("app_payload_B")
    assert abs(float(apw_idx.loc[600, "wire_tx_time_us_100Mbps"]) - 53.28) < 1e-6
    assert abs(float(apw_idx.loc[11500, "wire_tx_time_us_100Mbps"]) - 957.76) < 1e-6

    # (label, tx_us, n_frames, own_gate_us, category_color)
    # Categories: fits own gate (#009E73), exceeds TC3 100 us (#E69F00), exceeds all <=500 us gates (#D55E00)
    rows = [
        ("Sim. DDS [200 B, TC2]", 21.60, 1, 200.0, "#009E73"),
        ("VDA 5050 (1,0) [300 B, TC3]", 29.28, 1, 100.0, "#009E73"),
        ("Sim. Orders [600 B, TC3]", 53.28, 1, 100.0, "#009E73"),
        ("Sim. State [1,000 B, TC1]", 85.60, 1, 200.0, "#009E73"),
        ("Sim. Telemetry [1,400 B, TC0]", 117.60, 1, 500.0, "#009E73"),
        ("Max Unfrag. UDP / IPv4 MTU [1,472 B, TC0]", 123.36, 1, 500.0, "#009E73"),
        ("Frag. UDP [1,500 B, TC0]", 130.56, 2, 500.0, "#009E73"),
        ("VDA 5050 (4,3) [2,100 B, TC3]", 177.92, 2, 100.0, "#E69F00"),
        ("VDA 5050 (10,9) [5,000 B, TC3]", 419.20, 4, 100.0, "#E69F00"),
        ("VDA 5050 (20,19) [11,500 B, TC3]", 957.76, 8, 100.0, "#D55E00"),
    ]
    fig, ax = plt.subplots(figsize=(9.0, 4.1), constrained_layout=True)
    y_pos = np.arange(len(rows))
    tx_us = [r[1] for r in rows]
    colors = [r[4] for r in rows]
    ax.barh(y_pos, tx_us, height=0.66, color=colors, edgecolor="#1f2937", lw=0.5)
    for yi, (_lbl, tus, nfr, _g, _c) in enumerate(rows):
        ax.text(tus + 14.0, yi, f"{tus:.1f} us ({nfr}f)", va="center", ha="left", fontsize=8.0,
                bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none", alpha=0.88), zorder=4)
    l1 = ax.axvline(100.0, color="#009E73", ls="--", lw=1.5, label=r"TC3 Orders Gate ($100\;\mu\mathrm{s}$)")
    l2 = ax.axvline(200.0, color="#E69F00", ls=":", lw=1.6, label=r"TC1/TC2 State & DDS ($200\;\mu\mathrm{s}$)")
    l3 = ax.axvline(500.0, color="#0072B2", ls="-.", lw=1.5, label=r"TC0 Telemetry Gate ($500\;\mu\mathrm{s}$)")
    p1 = Patch(fc="#009E73", ec="#1f2937", lw=0.5, label="Fits assigned GCL window")
    p2 = Patch(fc="#E69F00", ec="#1f2937", lw=0.5, label=r"Exceeds TC3 ($100\;\mu\mathrm{s}$)")
    p3 = Patch(fc="#D55E00", ec="#1f2937", lw=0.5, label=r"Exceeds all gates ($>500\;\mu\mathrm{s}$)")
    ax.set_yticks(y_pos)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.2)
    ax.set_xlim(0, 1140.0)
    ax.set_xlabel(r"Wire Serialization Time on $100\;\mathrm{Mbps}$ Fast Ethernet ($\mu\mathrm{s}$)")
    ax.legend(handles=[l1, l2, l3, p1, p2, p3], loc="lower right", ncol=2, fontsize=7.6, framealpha=0.95)
    _save_pdf(fig, "fig_vda_gcl.pdf")


def make_fig_isolated_upgrades(s_knee: pd.DataFrame, s_supp: pd.DataFrame) -> None:
    """§5.1 isolated wired load knee and wireless fleet scaling (1x2)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.2, 4.4), constrained_layout=True)

    # Panel (A): Wired Transition vs Load (knee_r3, N=20, 54M)
    sub = _pick_pt(s_knee, N_AMR=20, phy_rate_Mbps=54).sort_values("lambda_tel_Mbps")
    specs_a = [
        (1, "dds", "miss_B_5ms", r"DDS ($\mathrm{Miss}_B$, $D=5$ ms) — Cell 1 (FIFO)", WIRED_COLOR["FIFO"], "-", "o"),
        (1, "dds", "miss_A_5ms", r"DDS (Watchdog $\mathrm{Miss}_A$) — Cell 1 (FIFO)", "#7F1D1D", "-.", "x"),
        (1, "state", "miss_B_50ms", r"State ($D=50$ ms) — Cell 1 (FIFO)", WIRED_COLOR["FIFO"], "--", "s"),
        (1, "telemetry", "miss_B_100ms", "Telemetry — Cell 1 (FIFO, 80 pkt)", WIRED_COLOR["FIFO"], ":", "^"),
        (3, "dds", "miss_B_5ms", r"DDS & State — Cells 3 & 5 (0.00%)", WIRED_COLOR["Priority"], "--", "D"),
        (3, "telemetry", "miss_B_100ms", "Telemetry — Cell 3 (802.1Q, 20 pkt)", WIRED_COLOR["Priority"], "-", "s"),
        (5, "telemetry", "miss_B_100ms", "Telemetry — Cell 5 (TAS, 44.8M cap)", WIRED_COLOR["TAS"], "-", "^"),
    ]
    for cell, cls, col, lbl, clr, ls, mk in specs_a:
        d = sub[(sub["cell"] == cell) & (sub["class"] == cls)]
        ax1.plot(d["lambda_tel_Mbps"], 100.0 * d[col], label=lbl, color=clr, ls=ls, marker=mk, ms=4.8, lw=1.8)
    ax1.axvline(44.8, color=WIRED_COLOR["TAS"], ls=":", lw=1.25)
    ax1.annotate("TAS TC0 cap\n(44.8 Mbps)", xy=(44.8, 18.0), xytext=(22.5, 31.0),
                 arrowprops=dict(arrowstyle="->", color=WIRED_COLOR["TAS"], lw=1.0),
                 fontsize=8.0, color="#065f46", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#a7f3d0"))
    ax1.axvspan(85.0, 95.0, color="#e5e7eb", alpha=0.55, zorder=0)
    ax1.annotate("FIFO saturation\nbracket (85–95 Mbps)", xy=(92.0, 48.0), xytext=(126.0, 84.0),
                 ha="center", arrowprops=dict(arrowstyle="->", color="#4b5563", lw=1.0),
                 fontsize=7.8, color="#1f2937",
                 bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#d1d5db", alpha=0.95))
    ax1.set_title(r"(A) Wired Sweep vs. Load ($N_{\mathrm{AMR}}=20$, 54 Mbps)")
    ax1.set_xlabel(r"Offered Telemetry Payload Load $\lambda_{\mathrm{tel}}$ (Mbps)")
    ax1.set_ylabel(r"Deadline Miss $\mathrm{Miss}_B$ / $\mathrm{Miss}_A$ (%)")
    ax1.set_ylim(-2.5, 108.0)
    ax1.legend(loc="upper left", fontsize=7.0, framealpha=0.94)

    # Panel (B): Wireless Scaling vs Fleet Size (supp_maxr, lambda=22.4M)
    sub_b = _pick_pt(s_supp, lambda_tel_Mbps=22.4).sort_values("N_AMR")
    specs_b = [
        (1, "orders", 12, "miss_B_50ms", "Orders (12M DL) — Cell 1 (CSMA/CA)", "#B91C1C", "-", "o"),
        (2, "orders", 12, "miss_B_50ms", "Orders (12M DL) — Cell 2 (TDMA)", "#B91C1C", "--", "s"),
        (1, "state", 12, "miss_B_50ms", "State (12M UL) — Cell 1 (CSMA/CA)", "#0072B2", "-", "^"),
        (2, "state", 12, "miss_B_50ms", "State (12M UL) — Cell 2 (TDMA)", "#0072B2", "--", "D"),
        (1, "orders", 54, "miss_B_50ms", "Orders & State (54M) — Cells 1 & 2 (0%)", "#009E73", ":", "v"),
    ]
    for cell, cls, phy, col, lbl, clr, ls, mk in specs_b:
        d = sub_b[(sub_b["cell"] == cell) & (sub_b["class"] == cls) & (sub_b["phy_rate_Mbps"] == phy)]
        ax2.plot(d["N_AMR"], 100.0 * d[col], label=lbl, color=clr, ls=ls, marker=mk, ms=4.8, lw=1.8)
    ord_n40 = 100.0 * float(
        sub_b[(sub_b["cell"] == 2) & (sub_b["class"] == "orders") & (sub_b["phy_rate_Mbps"] == 12) & (sub_b["N_AMR"] == 40)][
            "miss_B_50ms"
        ].iloc[0]
    )
    st_n40 = 100.0 * float(
        sub_b[(sub_b["cell"] == 2) & (sub_b["class"] == "state") & (sub_b["phy_rate_Mbps"] == 12) & (sub_b["N_AMR"] == 40)][
            "miss_B_50ms"
        ].iloc[0]
    )
    ax2.annotate(
        f"N=40 ($T_{{\\mathrm{{super}}}}=42$ ms):\nAP 10-slot burst spillover\n(Orders {ord_n40:.1f}%, State {st_n40:.1f}%)",
        xy=(40, ord_n40),
        xytext=(11, 24.0),
        arrowprops=dict(arrowstyle="->", color="#B91C1C", lw=1.0),
        fontsize=7.8,
        color="#7F1D1D",
        bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#fecaca"),
    )
    ax2.set_xticks([5, 10, 20, 40, 80])
    ax2.set_ylim(-3.0, 104.0)
    ax2.set_title(r"(B) Wireless Scaling vs. Fleet Size ($\lambda_{\mathrm{tel}}=22.4$ Mbps)")
    ax2.set_xlabel(r"AMR Fleet Size $N_{\mathrm{AMR}}$")
    ax2.set_ylabel(r"Nominal Deadline Miss $\mathrm{Miss}_B$ (%)")
    ax2.legend(loc="upper left", fontsize=7.4, framealpha=0.94)

    _save_pdf(fig, "fig_isolated_upgrades.pdf")


def make_fig_unpooled_n80(reps_supp: pd.DataFrame, bm_supp: pd.DataFrame) -> None:
    """Unpooled TDMA upgrade contrast Delta_W at (N=80, 12M), confirmatory CI + R=3 raw dots."""
    sub = reps_supp[(reps_supp["N_AMR"] == 80) & (reps_supp["phy_rate_Mbps"] == 12)].copy()
    bb = bm_supp[bm_supp["dominant_bottleneck"] == "structural_schedule_wait"]
    structural = {(r["class"], int(r["N_AMR"]), int(r["phy_rate_Mbps"]), round(float(r["lambda_tel_Mbps"]), 3))
                  for _, r in bb.iterrows()}
    f11b_classes = [
        ("orders", r"(A) Orders ($D = 50$ ms)"),
        ("dds", r"(B) DDS ($D = 5$ ms)"),
        ("state", r"(C) State ($D = 50$ ms)"),
    ]
    pairs = [
        ("FIFO (C1 − C2)", 1, 2, WIRED_COLOR["FIFO"]),
        ("802.1Q (C3 − C4)", 3, 4, WIRED_COLOR["Priority"]),
        ("802.1Qbv TAS (C5 − C6)", 5, 6, WIRED_COLOR["TAS"]),
    ]
    lams = sorted(sub["lambda_tel_Mbps"].unique())
    t_crit = {4: 2.776, 14: 2.145, 21: 2.080}

    records = []
    for cls, _clbl in f11b_classes:
        dc = sub[sub["class"] == cls].copy()
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
                ci = t_crit[n - 1] * float(diff.std(ddof=1)) / np.sqrt(n) if n >= 5 else np.nan
                records.append({
                    "class": cls, "lam": float(lam), "pair": pname,
                    "mean": float(diff.mean()), "ci": ci, "n": n, "raw": diff,
                })
    df_eff = pd.DataFrame(records)

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.4), constrained_layout=True)
    for ax, (cls, clbl) in zip(axes, f11b_classes):
        dc = df_eff[df_eff["class"] == cls]
        present_lams = sorted(dc["lam"].unique())
        x = np.arange(len(present_lams))
        w = 0.25
        for k, (pname, _ca, _cb, colour) in enumerate(pairs):
            dp = dc[dc["pair"] == pname].set_index("lam")
            for xi, lval in enumerate(present_lams):
                if lval not in dp.index:
                    continue
                row = dp.loc[lval]
                pos = x[xi] + (k - 1) * w
                bar = ax.bar(pos, row["mean"], w, color=colour, edgecolor="#111827", lw=0.45, zorder=2)[0]
                if (cls, 80, 12, round(float(lval), 3)) in structural:
                    bar.set_hatch("///")
                if row["n"] >= 5 and np.isfinite(row["ci"]):
                    ax.errorbar(pos, row["mean"], yerr=row["ci"], fmt="none",
                                ecolor="#111827", elinewidth=1.0, capsize=2.6, zorder=4)
                else:
                    # Exploratory R=3 slices: show exact raw seed outcomes + range instead of df=2 Student-t
                    raw = np.asarray(row["raw"], dtype=float)
                    ax.plot([pos, pos], [raw.min(), raw.max()], color="#374151", lw=1.0, zorder=4)
                    ax.scatter(np.full_like(raw, pos), raw, color="#ffffff", edgecolor="#111827",
                               s=18, lw=0.8, zorder=5)
        ax.axhline(0.0, color="#111827", lw=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{l:g}" for l in present_lams], fontsize=7.8)
        ax.set_xlabel(r"Offered Telemetry Load $\lambda_{\mathrm{tel}}$ (Mbps)", fontsize=8.8)
        ax.set_title(clbl)
        ax.set_ylabel(r"Wireless Gain $\Delta_{\mathrm{W}}$ (pp)")
        ax.grid(axis="y", alpha=0.28)

    handles = [Patch(fc=col, ec="#111827", lw=0.45, label=lbl) for lbl, _, _, col in pairs]
    handles.append(Patch(fc="white", ec="#111827", hatch="///", label=r"Structural Wait ($T_{\mathrm{super}} > D_c$)"))
    if (df_eff["n"] >= 5).any():
        r_vals = sorted({int(v) for v in df_eff.loc[df_eff["n"] >= 5, "n"]})
        r_str = f"R={r_vals[0]}" if len(r_vals) == 1 else "R \\in \\{" + ", ".join(str(r) for r in r_vals) + "\\}"
        handles.append(Line2D([0], [0], color="#111827", marker="_", lw=1.0, label=rf"95% Student-$t$ CI (${r_str}$)"))
    if (df_eff["n"] < 5).any():
        handles.append(Line2D([0], [0], color="#374151", marker="o", mfc="white", mec="#111827", ms=4.5, lw=1.0, label="Exploratory $R=3$ seeds + min–max"))
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.10), ncol=3, frameon=True, fontsize=7.8)
    _save_pdf(fig, "fig_unpooled_n80.pdf")


def make_fig_domain_drops(dd_knee: pd.DataFrame, dc_supp: pd.DataFrame) -> None:
    """Domain residence, wireless delay scaling, drop-cause anatomy, and per-AMR spread."""
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.0), constrained_layout=True)

    # Panel (A): Switch Residence vs Load (knee_r3, N=20, 54M) — Wired Discipline Palette
    ax = axes[0, 0]
    sub = _pick_pt(dd_knee, N_AMR=20, phy_rate_Mbps=54, domain="wired_switch")
    pts = sub.groupby(["cell", "class", "lambda_tel_Mbps"])["mean_ms"].mean().reset_index().sort_values("lambda_tel_Mbps")
    specs_a = [
        (1, "dds", "DDS / State / Tel — Cell 1 (FIFO)", WIRED_COLOR["FIFO"], "-", "o"),
        (3, "telemetry", "Telemetry — Cell 3 (802.1Q)", WIRED_COLOR["Priority"], "--", "s"),
        (3, "state", r"State / DDS — Cell 3 ($\approx 0.045$ ms)", WIRED_COLOR["Priority"], ":", "o"),
        (5, "telemetry", r"Telemetry — Cell 5 (TAS, $\geq 45$M cap)", WIRED_COLOR["TAS"], "-", "^"),
        (5, "orders", r"Orders — Cell 5 (TAS gate $\approx 0.55$ ms)", WIRED_COLOR["TAS"], "-.", "D"),
        (5, "state", r"State / DDS — Cell 5 (TAS gate $\approx 0.34$–$0.42$ ms)", WIRED_COLOR["TAS"], ":", "v"),
    ]
    for c, cls, lbl, clr, ls, mk in specs_a:
        d = pts[(pts["cell"] == c) & (pts["class"] == cls)]
        ax.plot(d["lambda_tel_Mbps"], d["mean_ms"], label=lbl, color=clr, ls=ls, marker=mk, ms=4.5, lw=1.7)
    ax.set_yscale("log")
    ax.set_ylim(8e-3, 90.0)
    ax.set_title(r"(A) Switch Residence $\tau_{\mathrm{switch}}$ vs. Load ($N_{\mathrm{AMR}}=20$, 54M)")
    ax.set_xlabel(r"Offered Telemetry Payload Load $\lambda_{\mathrm{tel}}$ (Mbps)")
    ax.set_ylabel("Mean Switch Residence Delay (ms, log)")
    ax.legend(loc="upper left", ncol=2, fontsize=6.8, framealpha=0.94)

    # Panel (B): Mean Wireless Delay vs Fleet Size (12M, 22.4M)
    ax = axes[0, 1]
    pts_b = _pick_pt(dc_supp, phy_rate_Mbps=12, lambda_tel_Mbps=22.4).sort_values("N_AMR")
    c1_n80 = float(pts_b[(pts_b["cell"] == 1) & (pts_b["class"] == "state") & (pts_b["N_AMR"] == 80)]["wireless_mean"].iloc[0])
    c2_n80 = float(pts_b[(pts_b["cell"] == 2) & (pts_b["class"] == "state") & (pts_b["N_AMR"] == 80)]["wireless_mean"].iloc[0])
    for c, cls, lbl, clr, ls, mk in [
        (1, "orders", "Orders (DL) — Cell 1 (CSMA/CA)", "#B91C1C", "-", "o"),
        (2, "orders", "Orders (DL) — Cell 2 (Scheduled TDMA)", "#B91C1C", "--", "s"),
        (1, "state", f"State (UL) — Cell 1 (CSMA/CA, {c1_n80:.1f} ms @ N=80)", "#0072B2", "-", "^"),
        (2, "state", f"State (UL) — Cell 2 (TDMA, {c2_n80:.1f} ms @ N=80)", "#0072B2", "--", "D"),
    ]:
        d = pts_b[(pts_b["cell"] == c) & (pts_b["class"] == cls)]
        ax.plot(d["N_AMR"], d["wireless_mean"], label=lbl, color=clr, ls=ls, marker=mk, ms=4.8, lw=1.8)
    ax.set_yscale("log")
    ax.set_xticks([5, 10, 20, 40, 80])
    ax.set_title(r"(B) Mean Wireless Delay $\tau_{\mathrm{wireless}}$ (12M, 22.4 Mbps)")
    ax.set_xlabel(r"AMR Fleet Size $N_{\mathrm{AMR}}$")
    ax.set_ylabel("Mean Wireless Delay (ms, log)")
    ax.legend(loc="upper left", fontsize=7.3, framealpha=0.94)

    # Panel (C): Drop & Termination Anatomy at N=80
    ax = axes[1, 0]
    bars_spec = [
        ("DDS C1\n(54M,149M)", 1, "dds", 80, 54, 149.3),
        ("Tel C1\n(54M,149M)", 1, "telemetry", 80, 54, 149.3),
        ("Tel C5\n(54M,149M)", 5, "telemetry", 80, 54, 149.3),
        ("State C1\n(12M,149M)", 1, "state", 80, 12, 149.3),
        ("State C3\n(12M,22M)", 3, "state", 80, 12, 22.4),
        ("State C5\n(12M,22M)", 5, "state", 80, 12, 22.4),
        ("Orders C1\n(12M,149M)", 1, "orders", 80, 12, 149.3),
        ("Orders C5\n(12M,149M)", 5, "orders", 80, 12, 149.3),
    ]
    q_arr, r_arr, lt_arr = [], [], []
    for _lbl, c, cls, n, p, l in bars_spec:
        row = _pick_pt(dc_supp, cell=c, **{"class": cls}, N_AMR=n, phy_rate_Mbps=p, lambda_tel_Mbps=l).iloc[0]
        q_arr.append(100.0 * float(row["p_drop_queue"]))
        r_arr.append(100.0 * float(row["p_drop_retry"]))
        lt_arr.append(100.0 * float(row["p_late_termination"]))
    q_arr, r_arr, lt_arr = np.array(q_arr), np.array(r_arr), np.array(lt_arr)
    xb = np.arange(len(bars_spec))
    ax.bar(xb, q_arr, width=0.62, color="#E69F00", edgecolor="#111827", lw=0.45, label=r"Queue Overflow ($p_{\mathrm{drop,Q}}$)")
    ax.bar(xb, r_arr, width=0.62, bottom=q_arr, color="#56B4E9", edgecolor="#111827", lw=0.45, label=r"MAC Retry Limit ($p_{\mathrm{drop,R}}$)")
    ax.bar(xb, lt_arr, width=0.62, bottom=q_arr + r_arr, color="#332288", edgecolor="#111827", lw=0.45, label=r"In-Flight at $t=60$ s ($p_{\mathrm{late}}$)")
    for xi, tot in zip(xb, q_arr + r_arr + lt_arr):
        ax.text(xi, tot + 1.2, f"{tot:.2f}%", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(xb)
    ax.set_xticklabels([b[0] for b in bars_spec], fontsize=7.4, rotation=16, ha="right")
    ax.set_ylim(0, 90.0)
    ax.set_title(r"(C) Unavailability Ledger ($N_{\mathrm{AMR}}=80$)")
    ax.set_ylabel("Share of Generated Valid Packets (%)")
    ax.legend(loc="upper right", fontsize=7.4, framealpha=0.94)

    # Panel (D): Per-AMR Orders Asymmetry at 12M, 22.4M
    ax = axes[1, 1]
    sub_d = _pick_pt(dc_supp, **{"class": "orders"}, phy_rate_Mbps=12, lambda_tel_Mbps=22.4).sort_values("N_AMR")
    c1 = sub_d[sub_d["cell"] == 1]
    c2 = sub_d[sub_d["cell"] == 2]
    c1_max80 = 100.0 * float(c1[c1["N_AMR"] == 80]["orders_amr_late_frac_max_mean"].iloc[0])
    c1_min80 = 100.0 * float(c1[c1["N_AMR"] == 80]["orders_amr_late_frac_min_mean"].iloc[0])
    c2_max80 = 100.0 * float(c2[c2["N_AMR"] == 80]["orders_amr_late_frac_max_mean"].iloc[0])
    c2_min80 = 100.0 * float(c2[c2["N_AMR"] == 80]["orders_amr_late_frac_min_mean"].iloc[0])
    ax.plot(c1["N_AMR"], 100.0 * c1["orders_amr_late_frac_max_mean"], color="#B91C1C", ls="-", marker="o", ms=4.5, label=f"Cell 1 (CSMA/CA) — Worst AMR ({c1_max80:.1f}%)")
    ax.plot(c1["N_AMR"], 100.0 * c1["orders_amr_late_frac_min_mean"], color="#B91C1C", ls="--", marker="s", ms=4.5, label=f"Cell 1 (CSMA/CA) — Best AMR ({c1_min80:.1f}%)")
    ax.fill_between(c1["N_AMR"], 100.0 * c1["orders_amr_late_frac_min_mean"], 100.0 * c1["orders_amr_late_frac_max_mean"], color="#B91C1C", alpha=0.14)
    ax.plot(c2["N_AMR"], 100.0 * c2["orders_amr_late_frac_max_mean"], color="#0072B2", ls="-", marker="o", ms=4.5, label=f"Cell 2 (TDMA) — Worst AMR ({c2_max80:.1f}%)")
    ax.plot(c2["N_AMR"], 100.0 * c2["orders_amr_late_frac_min_mean"], color="#0072B2", ls="--", marker="s", ms=4.5, label=f"Cell 2 (TDMA) — Best AMR ({c2_min80:.1f}%)")
    ax.fill_between(c2["N_AMR"], 100.0 * c2["orders_amr_late_frac_min_mean"], 100.0 * c2["orders_amr_late_frac_max_mean"], color="#0072B2", alpha=0.14)
    ax.set_xticks([5, 10, 20, 40, 80])
    ax.set_ylim(-3.0, 106.0)
    ax.set_title("(D) Per-AMR Downlink Orders Late Spread (12M, 22.4M)")
    ax.set_xlabel(r"AMR Fleet Size $N_{\mathrm{AMR}}$")
    ax.set_ylabel(r"Delivered Late Fraction ($> 50$ ms, %)")
    ax.legend(loc="upper left", fontsize=7.4, framealpha=0.94)

    _save_pdf(fig, "fig_domain_drops.pdf")


def make_fig_ecdf_n80(ecdf_supp: pd.DataFrame) -> None:
    """Rebuild F08 as crisp 2x2 log-log Complementary CDFs with shared axes & legend."""
    d = _pick_pt(ecdf_supp, N_AMR=80, phy_rate_Mbps=12, lambda_tel_Mbps=22.4)
    radio_ls = {"CSMA": "-", "Scheduled": "--"}
    cell_labels = {
        1: "C1: FIFO + CSMA",
        2: "C2: FIFO + TDMA",
        3: "C3: 802.1Q + CSMA",
        4: "C4: 802.1Q + TDMA",
        5: "C5: TAS + CSMA",
        6: "C6: TAS + TDMA",
    }
    classes = [
        ("dds", r"(A) DDS ($D_c = 5$ ms)", 5),
        ("state", r"(B) State ($D_c = 50$ ms)", 50),
        ("orders", r"(C) Orders ($D_c = 50$ ms)", 50),
        ("telemetry", r"(D) Telemetry ($D_c = 100$ ms)", 100),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(11.8, 7.2), constrained_layout=True)
    for idx, (ax, (cls, clbl, nom_d)) in enumerate(zip(axes.ravel(), classes)):
        for c, (rad, wrd) in CELLS.items():
            dc = d[(d["cell"] == c) & (d["class"] == cls) & (d["quantile_level"] < 0.9999)].sort_values("quantile_level")
            ccdf = np.maximum(1.0 - dc["quantile_level"], 1e-4)
            ax.plot(np.maximum(dc["delay_ms"], 2e-2), ccdf, drawstyle="steps-post",
                    lw=1.9, color=WIRED_COLOR[wrd], ls=radio_ls[rad])
        ax.axhline(0.01, color="#6b7280", ls=":", lw=1.0)
        ax.axvline(nom_d, color="#111827", ls="-.", lw=1.2)
        ax.text(nom_d * 0.88, 0.020, rf"$D_c={nom_d}$ ms", ha="right", va="bottom", fontsize=8.0,
                bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none", alpha=0.88))
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(8e-4, 1.35)
        if idx == 0:
            ax.set_xlim(right=8.0)
        ax.set_title(clbl)
        if idx in (2, 3):
            ax.set_xlabel("Delivered End-to-End Delay (ms, log scale)")
        if idx in (0, 2):
            ax.set_ylabel(r"Exceedance $P(\tau > x)$ (log scale)")
        ax.grid(alpha=0.25, which="both")

    handles = [Line2D([0], [0], label=cell_labels[c], lw=1.9,
                      color=WIRED_COLOR[wrd], ls=radio_ls[rad]) for c, (rad, wrd) in CELLS.items()]
    handles.append(Line2D([0], [0], color="#6b7280", ls=":", lw=1.1, label=r"$10^{-2}$ exceedance ($p_{99}$)"))
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.075), ncol=4, frameon=True, fontsize=8.0)
    _save_pdf(fig, "fig_ecdf_n80.pdf")


def make_fig_domain_bars(dd_supp: pd.DataFrame) -> None:
    """Vector 3-panel domain-delay bars showing ALL 6 cells across all 3 benchmarks."""
    benchmarks = [
        ("(A) Wired Saturation (40, 54M, 149.3M)", 40, 54, 149.3, 24.0),
        ("(B) Wireless Saturation (80, 12M, 22.4M)", 80, 12, 22.4, 148.0),
        ("(C) Dual Stress (80, 12M, 149.3M)", 80, 12, 149.3, 122.0),
    ]
    sub = dd_supp[dd_supp["class"] == "state"]
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.1), constrained_layout=True)

    for idx, (ax, (title, N, phy, lam, ymax)) in enumerate(zip(axes, benchmarks)):
        pt = _pick_pt(sub, N_AMR=N, phy_rate_Mbps=phy, lambda_tel_Mbps=lam)
        vals = pt.groupby(["cell", "domain"]).apply(
            lambda g: float((g["mean_ms"] * g["n_samples"]).sum() / g["n_samples"].sum())
        ).unstack("domain").reindex([1, 2, 3, 4, 5, 6])
        sw = vals["wired_switch"].to_numpy()
        wr = vals["wire_serialization"].to_numpy()
        wl = vals["wireless"].to_numpy()
        x = np.arange(6)
        ax.bar(x, sw, width=0.64, color=DOMAIN_COLOR["wired_switch"], label=r"Wired switch ($\tau_{\mathrm{switch}}$)")
        ax.bar(x, wr, width=0.64, bottom=sw, color=DOMAIN_COLOR["wire_serialization"], label=r"Wire serialization ($\tau_{\mathrm{wire}}$)")
        ax.bar(x, wl, width=0.64, bottom=sw + wr, color=DOMAIN_COLOR["wireless"], label=r"Wireless hop ($\tau_{\mathrm{wireless}}$)")
        totals = sw + wr + wl
        eff_ymax = max(ymax, float(totals.max()) * 1.18)
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + eff_ymax * 0.018, f"{tot:.1f}", ha="center", va="bottom", fontsize=7.8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"C{c}" for c in range(1, 7)], fontsize=8.6)
        ax.set_ylim(0, eff_ymax)
        ax.set_title(title, fontsize=9.6)
        if idx == 0:
            ax.set_ylabel("Mean Delivered State Delay (ms)")

    handles = [
        Patch(fc=DOMAIN_COLOR["wired_switch"], label=r"Wired switch ($\tau_{\mathrm{switch}}$)"),
        Patch(fc=DOMAIN_COLOR["wire_serialization"], label=r"Wire serialization ($\tau_{\mathrm{wire}}$, 0.17 ms)"),
        Patch(fc=DOMAIN_COLOR["wireless"], label=r"Wireless hop ($\tau_{\mathrm{wireless}}$)"),
    ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.09), ncol=3, frameon=True, fontsize=8.3)
    _save_pdf(fig, "fig_domain_bars.pdf")


def make_fig_conformance_bars(env_df: pd.DataFrame) -> None:
    """Stacked Confirmatory/Exploratory Option A operating-envelope bars (supp_maxR)."""
    import matplotlib.colors as mcolors

    cells = [1, 2, 3, 4, 5, 6]
    cats = [
        ("dds", r"DDS ($D=5$ ms, equal pass count)", "#56B4E9"),
        ("state", r"State ($D=50$ ms, $\mathrm{Miss}_B$)", "#E69F00"),
        ("orders", r"Orders ($D=50$ ms, $\mathrm{Miss}_B$)", "#009E73"),
        ("telemetry", r"Telemetry ($D=100$ ms, $\mathrm{Miss}_B$)", "#CC79A7"),
        ("joint3_B", r"Joint 3-Class ($\mathrm{Miss}_B$)", "#0072B2"),
        ("joint3_eff", r"Joint 3-Class (KILL $\mathrm{Miss}_A$ / ZOH $\mathrm{Miss}_B$)", "#332288"),
    ]
    w = 0.135
    x0 = np.arange(len(cells))
    offsets = np.linspace(-2.5 * w, 2.5 * w, len(cats))

    crit = env_df[env_df["class"].isin(["dds", "state", "orders"])]
    piv_b = crit.pivot(
        index=["cell", "stratum", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"],
        columns="class", values="state_B",
    )
    piv_e = crit.pivot(
        index=["cell", "stratum", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"],
        columns="class", values="state_eff",
    )
    j3_b = ((piv_b["dds"] == "all_le") & (piv_b["state"] == "all_le") & (piv_b["orders"] == "all_le"))
    j3_e = ((piv_e["dds"] == "all_le") & (piv_e["state"] == "all_le") & (piv_e["orders"] == "all_le"))

    fig, ax = plt.subplots(figsize=(11.0, 4.6), constrained_layout=True)
    for idx_k, (ckey, clbl, clr) in enumerate(cats):
        conf_vals, expl_vals = [], []
        for c in cells:
            if ckey == "joint3_B":
                sub_s = j3_b.xs(c, level="cell")
                conf_v = int(sub_s.xs("confirmatory", level="stratum").sum())
                expl_v = int(sub_s.xs("exploratory", level="stratum").sum())
            elif ckey == "joint3_eff":
                sub_s = j3_e.xs(c, level="cell")
                conf_v = int(sub_s.xs("confirmatory", level="stratum").sum())
                expl_v = int(sub_s.xs("exploratory", level="stratum").sum())
            else:
                sub_c = env_df[(env_df["cell"] == c) & (env_df["class"] == ckey) & (env_df["state_B"] == "all_le")]
                conf_v = int((sub_c["stratum"] == "confirmatory").sum())
                expl_v = int((sub_c["stratum"] == "exploratory").sum())
            conf_vals.append(conf_v)
            expl_vals.append(expl_v)

        conf_arr = np.array(conf_vals)
        expl_arr = np.array(expl_vals)
        tot_arr = conf_arr + expl_arr
        xs = x0 + offsets[idx_k]

        rgb = np.array(mcolors.to_rgb(clr))
        pastel_clr = tuple(0.64 * np.ones(3) + 0.36 * rgb)
        ax.bar(xs, conf_arr, width=w, color=clr, edgecolor="#111827", lw=0.55, zorder=3)
        ax.bar(xs, expl_arr, bottom=conf_arr, width=w,
               facecolor=pastel_clr, edgecolor="#111827",
               hatch="///", lw=0.55, zorder=3)

        for xi, cv, tot in zip(xs, conf_arr, tot_arr):
            ax.text(xi, float(tot) + 1.2, str(int(tot)),
                    ha="center", va="bottom", fontsize=7.4,
                    bbox=dict(boxstyle="square,pad=0.06", fc="white", ec="none", alpha=0.88),
                    zorder=5)
            if cv >= 8:
                ax.text(xi, float(cv) * 0.5, str(int(cv)),
                        ha="center", va="center", fontsize=6.8,
                        color="white", fontweight="bold", zorder=5)

    n_conf = int((env_df[(env_df["cell"] == 1) & (env_df["class"] == "dds")]["stratum"] == "confirmatory").sum())
    n_expl = 80 - n_conf
    expl_r_vals = sorted({int(v) for v in env_df.loc[env_df["stratum"] == "exploratory", "n_reps"]})
    expl_r_str = (
        f"R={expl_r_vals[0]}"
        if len(expl_r_vals) == 1
        else "R \\in \\{" + ",".join(str(r) for r in expl_r_vals) + "\\}"
    )

    ax.axhline(float(n_conf), color="#6b7280", ls="--", lw=1.0, zorder=2)
    ax.axhline(80.0, color="#374151", ls=":", lw=1.1, zorder=2)
    ax.text(-0.42, 82.0, "Full factorial grid: 80 pts",
            fontsize=8.0, color="#374151", va="bottom")
    ax.set_xticks(x0)
    ax.set_xticklabels(["C1\nFIFO+CSMA", "C2\nFIFO+TDMA", "C3\n802.1Q+CSMA", "C4\n802.1Q+TDMA", "C5\nTAS+CSMA", "C6\nTAS+TDMA"])
    ax.set_ylabel(r"Operating Points Passing All Seeds ($\max_r Y_r \leq 1.0\%$)")
    ax.set_ylim(0, 118.0)

    handles = [Patch(fc=clr, ec="#111827", lw=0.55, label=clbl) for _, clbl, clr in cats]
    pastel_gray = tuple(0.64 * np.ones(3) + 0.36 * np.array(mcolors.to_rgb("#6b7280")))
    handles.extend([
        Patch(fc="#6b7280", ec="#111827", lw=0.55, label=rf"Confirmatory Core ($R=22$, /{n_conf}, $p_{{\mathrm{{ok}}}} \geq 87.27\%$)"),
        Patch(fc=pastel_gray, ec="#111827", hatch="///", lw=0.55, label=rf"Exploratory Grid (${expl_r_str}$, /{n_expl})"),
        Line2D([0], [0], color="#6b7280", ls="--", lw=1.0, label=f"Confirmatory ceiling ({n_conf} pts)"),
    ])
    ax.legend(handles=handles, loc="upper center", ncol=3, frameon=True, fontsize=7.6)
    _save_pdf(fig, "fig_conformance_bars.pdf")


def make_fig_migration_heatmaps(bm_supp: pd.DataFrame, s_supp: pd.DataFrame) -> None:
    """3x1 stacked bottleneck migration heatmaps preserving numeric gains under hatching."""
    import matplotlib.patheffects as pe
    rows_spec = [(phy, n) for phy in (12, 54) for n in (5, 10, 20, 40, 80)]
    ylabels = [f"{phy}M | N={n}" for phy, n in rows_spec]
    cat_colors = {
        "none_or_uncongested": "#e5e7eb",
        "mixed_or_uncertain": "#fde2d2",
        "wired": "#f4976c",
        "scheduled_radio_penalty": "#60a5fa",
        "structural_schedule_wait": "#2563eb",
        "pending_nov22": "#fef9c3",
        "pending_p4": "#f9fafb",
    }
    ord_gains = {}
    s_ord = s_supp[s_supp["class"] == "orders"]
    for (phy, n, lam), grp in s_ord.groupby(["phy_rate_Mbps", "N_AMR", "lambda_tel_Mbps"]):
        c1 = grp[grp["cell"] == 1]["miss_B_50ms"]
        c2 = grp[grp["cell"] == 2]["miss_B_50ms"]
        if not c1.empty and not c2.empty:
            ord_gains[(int(phy), int(n), float(lam))] = 100.0 * (float(c1.iloc[0]) - float(c2.iloc[0]))

    fig, axes = plt.subplots(3, 1, figsize=(10.5, 9.8), constrained_layout=True)

    def _draw_hm(ax, cls_name: str, title: str, metric_mode: str):
        grid = np.zeros((len(rows_spec), len(LOADS_8), 3))
        texts = [[""] * len(LOADS_8) for _ in range(len(rows_spec))]
        text_colors = [["#111827"] * len(LOADS_8) for _ in range(len(rows_spec))]
        hatched = [[False] * len(LOADS_8) for _ in range(len(rows_spec))]
        has_p_n80 = False
        has_p_n5 = False
        sub = bm_supp[bm_supp["class"] == cls_name]
        for r_i, (phy, n) in enumerate(rows_spec):
            for c_j, lam in enumerate(LOADS_8):
                hit = _pick_pt(sub, phy_rate_Mbps=phy, N_AMR=n, lambda_tel_Mbps=lam)
                if hit.empty:
                    if n == 80:
                        has_p_n80 = True
                    else:
                        has_p_n5 = True
                    hex_c = cat_colors["pending_nov22"] if n == 80 else cat_colors["pending_p4"]
                    texts[r_i][c_j] = "Nov 22" if n == 80 else "P4"
                    text_colors[r_i][c_j] = "#9ca3af"
                else:
                    row = hit.iloc[0]
                    cat = str(row["dominant_bottleneck"])
                    if metric_mode == "orders" and cat == "wired" and abs(float(row["wired_fifo_to_priority_gain"])) < 1e-6:
                        # Override automated zero-wired-gain tie-breaker on N=10, 12M Orders rows (Table 13)
                        cat = "mixed_or_uncertain"
                    hex_c = cat_colors.get(cat, "#ffffff")
                    if cat == "none_or_uncongested":
                        texts[r_i][c_j] = "0 pp"
                    elif cat == "structural_schedule_wait":
                        hatched[r_i][c_j] = True
                        if metric_mode == "orders":
                            wg = row["wireless_gain"]
                            w_pct = 100.0 * float(wg) if pd.notna(wg) else ord_gains.get((phy, n, float(lam)), 0.0)
                            hex_c = "#009E73"
                            texts[r_i][c_j] = f"{w_pct:+.0f} pp"
                        else:
                            p_pct = 100.0 * float(row["wired_fifo_to_priority_gain"])
                            texts[r_i][c_j] = f"+{p_pct:.0f} pp" if abs(p_pct) >= 1.0 else "0 pp"
                        text_colors[r_i][c_j] = "#ffffff"
                    elif cat == "wired":
                        p_pct = 100.0 * float(row["wired_fifo_to_priority_gain"])
                        texts[r_i][c_j] = f"+{p_pct:.0f} pp"
                    elif cat == "scheduled_radio_penalty":
                        w_pct = 100.0 * float(row["wireless_gain"])
                        texts[r_i][c_j] = f"{w_pct:.1f} pp"
                    else:
                        w_pct = 100.0 * float(row["wireless_gain"]) if pd.notna(row["wireless_gain"]) else 0.0
                        p_pct = 100.0 * float(row["wired_fifo_to_priority_gain"])
                        val = p_pct if abs(p_pct) > abs(w_pct) else w_pct
                        texts[r_i][c_j] = "<0.1 pp" if abs(val) < 0.05 else f"{val:+.1f} pp"
                grid[r_i, c_j, :] = matplotlib.colors.to_rgb(hex_c)
        ax.imshow(grid, aspect="auto")
        for r_i in range(len(rows_spec)):
            for c_j in range(len(LOADS_8)):
                if hatched[r_i][c_j]:
                    rect = matplotlib.patches.Rectangle(
                        (c_j - 0.5, r_i - 0.5), 1.0, 1.0,
                        fill=False, edgecolor="#ffffff", hatch="///", alpha=0.40, lw=0.0, zorder=2
                    )
                    ax.add_patch(rect)
                effects = ([pe.withStroke(linewidth=2.4, foreground="#0f172a")]
                           if text_colors[r_i][c_j] == "#ffffff" else None)
                ax.text(c_j, r_i, texts[r_i][c_j], ha="center", va="center",
                        fontsize=7.9, color=text_colors[r_i][c_j],
                        fontweight="bold" if text_colors[r_i][c_j] == "#ffffff" else "normal",
                        path_effects=effects, zorder=4)
        for r_i in range(len(rows_spec) + 1):
            ax.axhline(r_i - 0.5, color="#cbd5e1", lw=0.6, zorder=3)
        for c_j in range(len(LOADS_8) + 1):
            ax.axvline(c_j - 0.5, color="#cbd5e1", lw=0.6, zorder=3)
        ax.axhline(4.5, color="#111827", ls="--", lw=1.3, zorder=5)
        ax.set_yticks(range(len(rows_spec)))
        ax.set_yticklabels(ylabels, fontsize=7.9)
        ax.set_xticks(range(len(LOADS_8)))
        ax.set_xticklabels([f"{l:g}" for l in LOADS_8], fontsize=8.3)
        ax.set_title(title)
        ax.grid(False)
        return has_p_n80, has_p_n5

    p80_a, p5_a = _draw_hm(axes[0], "state", r"(A) State ($D_c = 50$ ms): Wired Priority Gain $\Delta_{\mathrm{P}}$ (pp)", "state")
    p80_b, p5_b = _draw_hm(axes[1], "orders", r"(B) Orders ($D_c = 50$ ms): Wireless TDMA Gain $\Delta_{\mathrm{W}}$ (pp)", "orders")
    p80_c, p5_c = _draw_hm(axes[2], "dds", r"(C) DDS ($D_c = 5$ ms): Wired Priority Gain $\Delta_{\mathrm{P}}$ (pp)", "dds")
    axes[2].set_xlabel(r"Offered Telemetry Payload Load $\lambda_{\mathrm{tel}}$ (Mbps)")

    handles = [
        Patch(fc=cat_colors["none_or_uncongested"], ec="#9ca3af", label="Uncongested (0 pp)"),
        Patch(fc=cat_colors["mixed_or_uncertain"], ec="#9ca3af", label="Mixed / Transition"),
        Patch(fc=cat_colors["wired"], ec="#9ca3af", label=r"Wired FIFO Bottleneck ($+\Delta_{\mathrm{P}}$)"),
        Patch(fc=cat_colors["scheduled_radio_penalty"], ec="#9ca3af", label=r"AP Spillover ($\Delta_{\mathrm{W}}$)"),
        Patch(fc=cat_colors["structural_schedule_wait"], ec="#ffffff", hatch="///", label=r"Structural Wait ($T_{\mathrm{super}}>D_c$, State)"),
        Patch(fc="#009E73", ec="#ffffff", hatch="///", label=r"TDMA Orders Rescue ($T_{\mathrm{super}}>D_c$)"),
    ]
    if p80_a or p80_b or p80_c:
        handles.append(Patch(fc=cat_colors["pending_nov22"], ec="#d1d5db", label="Pending Nov 22 (N=80)"))
    if p5_a or p5_b or p5_c:
        handles.append(Patch(fc=cat_colors["pending_p4"], ec="#d1d5db", label="Pending Stage P4 (N=5)"))
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.055), ncol=4 if len(handles) > 6 else 3, frameon=True, fontsize=7.8)
    _save_pdf(fig, "fig_migration_heatmaps.pdf")


def make_fig_wireless_diagnostics(cb: pd.DataFrame, ts: pd.DataFrame, da: pd.DataFrame, mp_supp: pd.DataFrame, mac_supp: pd.DataFrame) -> None:
    """§6.1 wireless collapse & spatial diagnostics — strictly single y-axis per panel."""
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.2), constrained_layout=True)

    # Panel (A): 45-seed Cell 1 outcome distribution at (80, 12M, 22.4M)
    ax = axes[0, 0]
    n_tot = len(cb)
    n_norm = int((cb["regime"] == "normal").sum())
    n_int = int((cb["regime"] == "intermediate").sum())
    n_col = int((cb["regime"] == "collapsed").sum())
    med_norm = 100.0 * float(cb[cb["regime"] == "normal"]["state_miss_B_50ms"].median())
    max_col = 100.0 * float(cb["state_miss_B_50ms"].max())
    max_rep = int(cb.loc[cb["state_miss_B_50ms"].idxmax(), "rep"])
    for reg, lbl, clr in [
        ("normal", f"Normal (<10%, n={n_norm}/{n_tot}, med {med_norm:.2f}%)", "#009E73"),
        ("intermediate", f"Intermediate (10–50%, n={n_int}/{n_tot})", "#E69F00"),
        ("collapsed", f"Collapsed (>=50%, n={n_col}/{n_tot}, r={max_rep}: {max_col:.1f}%)", "#D55E00"),
    ]:
        d = cb[cb["regime"] == reg]
        ax.scatter(d["state_p99_ms"], 100.0 * d["state_miss_B_50ms"], color=clr,
                   edgecolor="#111827", lw=0.55, s=46, label=lbl, zorder=3)
    ax.axhline(10.0, color="#E69F00", ls=":", lw=1.2, label="10% threshold")
    ax.axhline(50.0, color="#D55E00", ls="--", lw=1.2, label="50% collapse threshold")
    ax.set_xscale("log")
    ax.set_ylim(-3.0, 84.0)
    ax.set_title(r"(A) Cell 1 Seed Outcomes ($N_{\mathrm{AMR}}=80$, 12M, 22.4M, $R=45$)")
    ax.set_xlabel(r"State Tail Latency $p_{99}$ (ms, log scale)")
    ax.set_ylabel(r"State Deadline Miss $\mathrm{Miss}_B$ (%)")
    ax.legend(loc="upper left", fontsize=7.3, framealpha=0.94)

    # Panel (B): Temporal evolution on worst-case seed r=3
    ax = axes[0, 1]
    t1 = ts[(ts["cell"] == 1) & (ts["bin_s"] >= 5)].sort_values("bin_s")
    t5 = ts[(ts["cell"] == 5) & (ts["bin_s"] >= 5)].sort_values("bin_s")
    ax.axvspan(0, 5, color="#e5e7eb", alpha=0.65, zorder=0)
    ax.text(2.5, 50.0, "Warm-up\n(unrecorded)", ha="center", va="center", fontsize=7.5, color="#4b5563", rotation=90)
    ax.plot(t1["bin_s"], t1["ap_q_max"], color="#B91C1C", lw=1.9, label="AP Queue Max (C1/C3/C5, cap=100)")
    ax.plot(t1["bin_s"], t1["amr_q_mean"], color=WIRED_COLOR["Priority"], lw=1.8, label="AMRs Mean Queue (C1/C3 CSMA)")
    ax.plot(t5["bin_s"], t5["amr_q_mean"], color=WIRED_COLOR["TAS"], ls="--", lw=1.8, label="AMRs Mean Queue (C5 TAS+CSMA)")
    ax.plot(t1["bin_s"], t1["amr_retry_drops_count"], color="#E69F00", ls=":", lw=1.7, label="AMR Retry Drops/s (C1/C3)")
    ax.plot(t5["bin_s"], t5["sw_q_max"], color="#6b7280", ls="-.", lw=1.5, label="Switch TC1 Max Queue (C5 TAS)")
    ax.set_ylim(-2.0, 108.0)
    ax.set_title(r"(B) Worst-Case Seed $r=3$ Queue Dynamics (12M, 22.4M)")
    ax.set_xlabel("Simulation Time (s, 1-second bins)")
    ax.set_ylabel("Queue Occupancy (pkts) / Drops per Second")
    ax.legend(loc="center right", fontsize=7.1, framealpha=0.94)

    # Panel (C): Single-axis Uplink Spatial Gradient (r=3)
    ax = axes[1, 0]
    d1 = da[da["cell"] == 1]
    d5 = da[da["cell"] == 5]
    r1 = float(d1["dist_to_ap_m"].corr(d1["amr_mac_retry_drops"]))
    r5 = float(d5["dist_to_ap_m"].corr(d5["amr_mac_retry_drops"]))
    ax.scatter(d1["dist_to_ap_m"], d1["amr_mac_retry_drops"], color=WIRED_COLOR["Priority"], edgecolor="#111827",
               lw=0.4, alpha=0.82, s=36, label=rf"Cells 1 & 3 ($r_{{\mathrm{{dist}}}}={r1:.2f}$)")
    ax.scatter(d5["dist_to_ap_m"], d5["amr_mac_retry_drops"], color=WIRED_COLOR["TAS"], marker="^", edgecolor="#111827",
               lw=0.4, alpha=0.82, s=38, label=rf"Cell 5 ($r_{{\mathrm{{dist}}}}={r5:.2f}$)")
    x_line = np.linspace(float(d1["dist_to_ap_m"].min()), float(d1["dist_to_ap_m"].max()), 50)
    m1, b1 = np.polyfit(d1["dist_to_ap_m"], d1["amr_mac_retry_drops"], 1)
    m5, b5 = np.polyfit(d5["dist_to_ap_m"], d5["amr_mac_retry_drops"], 1)
    ax.plot(x_line, m1 * x_line + b1, color=WIRED_COLOR["Priority"], ls="--", lw=1.4)
    ax.plot(x_line, m5 * x_line + b5, color=WIRED_COLOR["TAS"], ls="-.", lw=1.4)
    ax.set_ylim(-2.0, 39.0)
    ax.set_title(r"(C) Per-AMR Uplink MAC Retry Drops vs. AP Distance ($r=3$)")
    ax.set_xlabel(r"Euclidean Distance to Access Point $d_i$ (m)")
    ax.set_ylabel("Uplink MAC Retry-Limit Drops per AMR (pkts)")
    ax.legend(loc="upper left", fontsize=7.8, framealpha=0.94)

    # Panel (D): Single-axis CSMA/CA MAC Retransmission Ratio Scaling (22.4M)
    ax = axes[1, 1]
    sub_m = _pick_pt(mp_supp, lambda_tel_Mbps=22.4).sort_values("N_AMR")
    c1_12 = sub_m[(sub_m["cell"] == 1) & (sub_m["phy_rate_Mbps"] == 12)]
    c5_12 = sub_m[(sub_m["cell"] == 5) & (sub_m["phy_rate_Mbps"] == 12)]
    c1_54 = sub_m[(sub_m["cell"] == 1) & (sub_m["phy_rate_Mbps"] == 54)]
    c2_12 = sub_m[(sub_m["cell"] == 2) & (sub_m["phy_rate_Mbps"] == 12)]
    tdma_mac = mac_supp[mac_supp["cell"].isin([2, 4, 6])]
    n_tdma_runs = len(tdma_mac)
    c2_rel = int(tdma_mac[tdma_mac["cell"] == 2]["ap_sched_grant_released"].sum())
    c4_rel = int(tdma_mac[tdma_mac["cell"] == 4]["ap_sched_grant_released"].sum())
    c6_rel = int(tdma_mac[tdma_mac["cell"] == 6]["ap_sched_grant_released"].sum())
    tdma_ret_max = 100.0 * float(tdma_mac["amr_tx_retry_ratio"].max())
    rel_str = (
        f"Cells 2 & 4: {c2_rel:,} each | Cell 6 (TAS): {c6_rel:,}"
        if c2_rel == c4_rel
        else f"Cell 2: {c2_rel:,}, Cell 4: {c4_rel:,} | Cell 6 (TAS): {c6_rel:,}"
    )
    ax.plot(c1_12["N_AMR"], 100.0 * c1_12["amr_tx_retry_ratio_mean"], color=WIRED_COLOR["FIFO"], marker="o", lw=1.8, label="AMR Retries — 12M CSMA (Cells 1 & 3)")
    ax.plot(c5_12["N_AMR"], 100.0 * c5_12["amr_tx_retry_ratio_mean"], color=WIRED_COLOR["TAS"], marker="^", ls="--", lw=1.7, label="AMR Retries — 12M CSMA (Cell 5 TAS)")
    ax.plot(c1_12["N_AMR"], 100.0 * c1_12["ap_tx_retry_ratio_mean"], color="#E69F00", ls=":", marker="s", lw=1.7, label="AP Retries — 12M CSMA (Cell 1)")
    ax.plot(c1_54["N_AMR"], 100.0 * c1_54["amr_tx_retry_ratio_mean"], color=WIRED_COLOR["Priority"], marker="D", lw=1.6, label=rf"AMR Retries — 54M CSMA ($\leq {100.0 * float(c1_54['amr_tx_retry_ratio_mean'].max()):.2f}\%$)")
    ax.plot(c2_12["N_AMR"], 100.0 * c2_12["amr_tx_retry_ratio_mean"], color="#111827", ls="-.", marker="v", ms=4.2, lw=1.4, label=rf"TDMA Cells 2/4/6 ({tdma_ret_max:.2f}% across {n_tdma_runs:,} runs)")
    ax.text(36.0, 14.5,
            f"AP trailing-edge grant releases\n({n_tdma_runs:,} TDMA runs):\n{rel_str}",
            ha="center", va="center", fontsize=7.6, color="#065f46",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#a7f3d0", alpha=0.95))
    ax.set_xticks([5, 10, 20, 40, 80])
    ax.set_ylim(-1.2, 31.0)
    ax.set_title(r"(D) Mean MAC Retransmission Ratio ($\lambda_{\mathrm{tel}}=22.4$ Mbps)")
    ax.set_xlabel(r"AMR Fleet Size $N_{\mathrm{AMR}}$")
    ax.set_ylabel("MAC Retransmission Ratio (%)")
    ax.legend(loc="upper left", fontsize=7.2, framealpha=0.94)

    _save_pdf(fig, "fig_wireless_diagnostics.pdf")


def make_fig_ner_interface(mr_core: pd.DataFrame, st_supp: pd.DataFrame,
                           g8b: pd.DataFrame, ecdf_knee: pd.DataFrame) -> None:
    """§6.2-§6.3 NER multirate, ZOH staleness, Leave-One-Out W1, and ECDFs."""
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.2), constrained_layout=True)

    # Panel (A): Multi-rate Tick Sensitivity (core_r3)
    ax = axes[0, 0]
    groups = [
        ("DDS\nC1/C2", "dds", [1, 2]),
        ("State\nC1", "state", [1]),
        ("State\nC2", "state", [2]),
        ("State\nC4/C6", "state", [4, 6]),
        ("Orders\nCSMA", "orders", [1, 3, 5]),
        ("Orders\nTDMA", "orders", [2, 4, 6]),
    ]
    metrics = [
        ("miss_A_nom", r"$\mathrm{Miss}_A$ (Continuous)", "#B91C1C"),
        ("miss_B_nom_T10ms", r"$\mathrm{Miss}_B$ ($T=10$ ms)", "#E69F00"),
        ("miss_B_nom_T50ms", r"$\mathrm{Miss}_B$ ($T=50$ ms)", "#009E73"),
        ("miss_B_nom_T500ms", r"$\mathrm{Miss}_B$ ($T=500$ ms)", "#0072B2"),
        ("miss_BT_L_eq_T10ms", r"$B^T$ ($L_c=T=10$ ms)", "#CC79A7"),
    ]
    x0 = np.arange(len(groups))
    w = 0.155
    offs = np.linspace(-2 * w, 2 * w, len(metrics))
    for k_i, (mcol, mlbl, clr) in enumerate(metrics):
        vals = []
        for _gname, cls, clist in groups:
            sub = mr_core[(mr_core["class"] == cls) & (mr_core["cell"].isin(clist))]
            vals.append(100.0 * float(sub[mcol].mean()))
        ax.bar(x0 + offs[k_i], vals, width=w, color=clr, edgecolor="#111827", lw=0.4, label=mlbl)
    ax.set_xticks(x0)
    ax.set_xticklabels([g[0] for g in groups], fontsize=8.1)
    ax.set_ylim(0, 50.0)
    ax.set_title("(A) Multi-Rate NER Tick Sensitivity (core-R3)")
    ax.set_ylabel("Balanced Grid Mean Miss Rate (%)")
    ax.legend(loc="upper right", fontsize=7.2, framealpha=0.94)

    # Panel (B): ZOH Staleness vs Fleet Size (supp_maxr, 12M, 22.4M)
    ax = axes[0, 1]
    st_state = st_supp[st_supp["class"] == "state"]
    max_c13 = int(round(float(st_state[st_state["cell"].isin([1, 3])]["stale10_max"].max())))
    max_c5 = int(round(float(st_state[st_state["cell"] == 5]["stale10_max"].max())))
    max_c2 = int(round(float(st_state[st_state["cell"] == 2]["stale10_max"].max())))
    max_c46 = int(round(float(st_state[st_state["cell"].isin([4, 6])]["stale10_max"].max())))
    sub_st = _pick_pt(st_state, phy_rate_Mbps=12, lambda_tel_Mbps=22.4).sort_values("N_AMR")
    for clist, lbl, clr, ls, mk in [
        ([1, 3], rf"Cells 1 & 3 (CSMA, max {max_c13:,} ticks)", WIRED_COLOR["Priority"], "-", "o"),
        ([5], rf"Cell 5 (TAS+CSMA, max {max_c5:,} ticks)", WIRED_COLOR["TAS"], "-", "^"),
        ([2], f"Cell 2 (FIFO+TDMA, max {max_c2:,} ticks)", WIRED_COLOR["FIFO"], "--", "D"),
        ([4, 6], f"Cells 4 & 6 (802.1Q/TAS+TDMA, max {max_c46:,} ticks)", "#0072B2", "--", "v"),
    ]:
        d = sub_st[sub_st["cell"].isin(clist)].groupby("N_AMR")["stale10_mean"].mean().reset_index()
        ax.plot(d["N_AMR"], d["stale10_mean"], label=lbl, color=clr, ls=ls, marker=mk, ms=4.8, lw=1.8)
    ax.set_yscale("symlog", linthresh=0.05)
    ax.set_ylim(-0.005, 34.0)
    ax.set_xticks([5, 10, 20, 40, 80])
    ax.annotate(r"Exact $0.00$ ticks for all $N_{\mathrm{AMR}} \leq 40$",
                xy=(25.0, 0.001), xytext=(11.0, 0.032),
                arrowprops=dict(arrowstyle="->", color="#374151", lw=0.9),
                fontsize=7.6, color="#1f2937",
                bbox=dict(boxstyle="round,pad=0.2", fc="#f8fafc", ec="#cbd5e1"))
    ax.set_title(r"(B) State ZOH Staleness $\Delta k_{\mathrm{stale},10}$ (12M, 22.4M)")
    ax.set_xlabel(r"AMR Fleet Size $N_{\mathrm{AMR}}$")
    ax.set_ylabel("Mean ZOH Excess Staleness (10 ms ticks)")
    ax.legend(loc="upper left", fontsize=7.1, framealpha=0.94)

    # Panel (C): Matched Leave-One-Out (LOO) W1 Error (N in {10,20,40})
    ax = axes[1, 0]
    g8_lam = g8b[g8b["mode"] == "lo_lambda_o"]
    for cls, clr, mk in [
        ("dds", "#B91C1C", "o"),
        ("state", "#0072B2", "s"),
        ("telemetry", "#009E73", "^"),
        ("orders", "#CC79A7", "D"),
    ]:
        for pool, ls, lbl_suffix in [
            ("core_r3", "--", "4-load"),
            ("knee_r3", "-", "8-load"),
        ]:
            d = g8_lam[(g8_lam["pool"] == pool) & (g8_lam["class"] == cls) & (g8_lam["N_AMR"].isin([10, 20, 40]))]
            d = d.groupby("held_value")["w1_ms"].mean().reset_index().sort_values("held_value")
            ax.plot(d["held_value"], d["w1_ms"], color=clr, ls=ls, marker=mk, ms=4.4, lw=1.7,
                    label=f"{cls.upper() if cls=='dds' else cls.capitalize()} ({lbl_suffix})")
    ax.annotate("Matched 74.7/95.0M:\n−70.0% to −71.1% W1 on eth[0]\n−33.2% on Orders (eth[1])",
                xy=(85.0, 0.94), xytext=(46.0, 1.38),
                arrowprops=dict(arrowstyle="->", color="#1f2937", lw=0.9), fontsize=7.3,
                bbox=dict(boxstyle="round,pad=0.22", fc="#f8fafc", ec="#cbd5e1"))
    ax.set_ylim(-0.10, 3.25)
    ax.set_title(r"(C) Leave-One-Out Load $\mathcal{W}_1$ Error ($N \in \{10,20,40\}$)")
    ax.set_xlabel(r"Held-Out Telemetry Payload Load $\lambda_{\mathrm{tel}}$ (Mbps)")
    ax.set_ylabel(r"Mean Wasserstein-1 Error $\mathcal{W}_1$ (ms)")
    ax.legend(loc="upper left", ncol=2, fontsize=6.7, framealpha=0.94)

    # Panel (D): 25-Quantile ECDFs (knee_r3, N=40, 12M, 149.3M) — legend outside cleanly!
    ax = axes[1, 1]
    sub_e = _pick_pt(ecdf_knee, N_AMR=40, phy_rate_Mbps=12, lambda_tel_Mbps=149.3)
    ecdf_specs = [
        (1, "dds", "DDS — C1 (FIFO)", WIRED_COLOR["FIFO"], ":"),
        (3, "dds", "DDS — C3 (802.1Q)", WIRED_COLOR["Priority"], ":"),
        (1, "state", "State — C1 (FIFO+CSMA)", WIRED_COLOR["FIFO"], "-"),
        (3, "state", "State — C3 (802.1Q+CSMA)", WIRED_COLOR["Priority"], "-"),
        (4, "state", "State — C4 (802.1Q+TDMA)", WIRED_COLOR["Priority"], "--"),
        (1, "orders", "Orders — C1 (CSMA)", "#B91C1C", "-."),
        (2, "orders", "Orders — C2 (TDMA)", WIRED_COLOR["FIFO"], "--"),
    ]
    for c, cls, lbl, clr, ls in ecdf_specs:
        d = sub_e[(sub_e["cell"] == c) & (sub_e["class"] == cls)].sort_values("quantile_level")
        ax.plot(d["delay_ms"], d["quantile_level"], label=lbl, color=clr, ls=ls, lw=1.7)
    ax.axvline(5.0, color="#6b7280", ls=":", lw=1.2)
    ax.axvline(50.0, color="#111827", ls=":", lw=1.2)
    ax.text(4.6, 0.96, "5 ms", ha="right", va="top", fontsize=7.6, bbox=dict(fc="white", ec="none", pad=0.6))
    ax.text(54.0, 0.96, "50 ms", ha="left", va="top", fontsize=7.6, bbox=dict(fc="white", ec="none", pad=0.6))
    ax.set_xscale("log")
    ax.set_ylim(-0.02, 1.04)
    ax.set_title(r"(D) Empirical 25-Quantile ECDFs ($N=40$, 12M, 149.3M)")
    ax.set_xlabel("End-to-End Delivery Delay (ms, log scale)")
    ax.set_ylabel("Cumulative Probability (ECDF Quantile)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=6.8, frameon=True)

    _save_pdf(fig, "fig_ner_interface.pdf")


def make_fig_runtime_speedup() -> None:
    """Appendix A Stage 0 192-pair (384-run) dry-run optimization speedup."""
    b_path = REPO_DIR / "evidence" / "05_dry_run" / "manifest.csv"
    o_path = REPO_DIR / "evidence" / "05_dry_run_opt" / "manifest.csv"
    if not (b_path.exists() and o_path.exists()):
        return
    base = pd.read_csv(b_path)
    opt = pd.read_csv(o_path)
    base = base[base["exit_code"] == 0].copy()
    opt = opt[opt["exit_code"] == 0].copy()
    conds = sorted({(int(a), t) for a, t in zip(opt["nAmr"], opt["telInterval"])},
                   key=lambda x: (TEL_MBPS.get(x[1], 0), x[0]))
    fig, (a, b) = plt.subplots(1, 2, figsize=(12.2, 4.2), gridspec_kw=dict(width_ratios=[1.18, 1.12]), constrained_layout=True)
    xs = np.arange(len(conds))
    width = 0.38
    mu_b = np.array([base[(base["nAmr"] == n) & (base["telInterval"] == t)]["wall_seconds"].mean() for n, t in conds])
    mu_o = np.array([opt[(opt["nAmr"] == n) & (opt["telInterval"] == t)]["wall_seconds"].mean() for n, t in conds])
    a.bar(xs - width / 2, mu_b / 60.0, width, label="Baseline (all vectors)", color="#9ca3af", edgecolor="#111827", lw=0.45)
    a.bar(xs + width / 2, mu_o / 60.0, width, label="Optimized (targeted recording)", color=WIRED_COLOR["Priority"], edgecolor="#111827", lw=0.45)
    a.set_xticks(xs)
    a.set_xticklabels([f"N={n}\n{TEL_MBPS.get(t, 0):g}M" for n, t in conds], fontsize=8.1)
    a.set_ylabel("Mean Wall Time per 60 s Run (min)")
    a.set_title("(A) Per-Run Simulation Wall Time vs. Load & Fleet")
    a.legend(loc="upper left", fontsize=8.0, framealpha=0.94)

    sp = mu_b / mu_o
    b.bar(xs, sp, color=WIRED_COLOR["TAS"], edgecolor="#111827", lw=0.45, width=0.55, zorder=3)
    for xi, v in zip(xs, sp):
        b.text(xi, v - 0.14, f"{v:.2f}×", ha="center", va="top", fontsize=7.9,
               color="white", fontweight="bold", zorder=5)
    tot_b = float(base["wall_seconds"].sum())
    tot_o = float(opt["wall_seconds"].sum())
    b.axhline(tot_b / tot_o, color="#111827", ls="--", lw=1.2, zorder=1,
              label=f"Aggregate speedup: {tot_b / tot_o:.2f}×")
    b.set_xticks(xs)
    b.set_xticklabels([f"N={n}\n{TEL_MBPS.get(t, 0):g}M" for n, t in conds], fontsize=8.1)
    b.set_ylim(0, max(sp) * 1.26)
    b.set_ylabel("Speedup Ratio (Baseline / Optimized)")
    b.set_title("(B) Equivalent-Scalar Speedup Factor (192 Pairs)")
    b.legend(loc="upper left", fontsize=8.0, framealpha=0.94)

    _save_pdf(fig, "fig_runtime_speedup.pdf")


def main() -> None:
    s_core = pd.read_csv(TBL_DIR / "core_r3" / "lookup_summary.csv")
    s_knee = pd.read_csv(TBL_DIR / "knee_r3" / "lookup_summary.csv")
    s_supp = pd.read_csv(TBL_DIR / "supp_maxr" / "lookup_summary.csv")
    dd_knee = pd.read_csv(TBL_DIR / "knee_r3" / "lookup_domain_delay.csv")
    dd_supp = pd.read_csv(TBL_DIR / "supp_maxr" / "lookup_domain_delay.csv")
    ecdf_knee = pd.read_csv(TBL_DIR / "knee_r3" / "lookup_ecdf.csv")
    ecdf_supp = pd.read_csv(TBL_DIR / "supp_maxr" / "lookup_ecdf.csv")
    bm_supp = pd.read_csv(TBL_DIR / "supp_maxr" / "bottleneck_migration.csv")
    reps_supp = pd.read_csv(TBL_DIR / "supp_maxr" / "lookup_replications.csv")

    cb = pd.read_csv(EXTRAS / "collapse_b_per_seed.csv")
    env_df = pd.read_csv(EXTRAS / "envelope_screen_option_a.csv")
    ts = pd.read_csv(EXTRAS / "diag_rep3_timeseries.csv")
    g8b = pd.read_csv(EXTRAS / "g8b_loo_error.csv")
    apw = pd.read_csv(EXTRAS / "analytic_payload_window.csv")
    da = pd.read_csv(EXTRAS / "diag_rep3_per_amr.csv")

    mr_core = pd.read_csv(EXTRAS / "multirate_summary.csv")
    mr_core = mr_core[mr_core["pool"] == "core_r3"]
    st_supp = pd.read_csv(EXTRAS / "staleness_summary.csv")
    st_supp = st_supp[st_supp["pool"] == "supp_maxr"]
    dc_supp = pd.read_csv(EXTRAS / "drop_cause_and_tail_summary.csv")
    dc_supp = dc_supp[dc_supp["pool"] == "supp_maxr"]
    mp_supp = pd.read_csv(EXTRAS / "mac_phy_summary.csv")
    mp_supp = mp_supp[mp_supp["pool"] == "supp_maxr"]
    mac_supp = pd.read_csv(EXTRAS / "run_mac_phy_stats.csv")
    mac_supp = mac_supp[mac_supp["in_supp_maxr"] == True]

    make_fig_vda_gcl(apw)
    make_fig_isolated_upgrades(s_knee, s_supp)
    make_fig_unpooled_n80(reps_supp, bm_supp)
    make_fig_domain_drops(dd_knee, dc_supp)
    make_fig_ecdf_n80(ecdf_supp)
    make_fig_domain_bars(dd_supp)
    make_fig_conformance_bars(env_df)
    make_fig_migration_heatmaps(bm_supp, s_supp)
    make_fig_wireless_diagnostics(cb, ts, da, mp_supp, mac_supp)
    make_fig_ner_interface(mr_core, st_supp, g8b, ecdf_supp)
    make_fig_runtime_speedup()
    print("[figs] Generated all 11 vector PDFs in", PDF_DIR)


if __name__ == "__main__":
    main()
