#!/usr/bin/env python3
"""Extract all verified numbers from report/Project Validation/tables/ for main.tex."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

TOOL_DIR = Path(__file__).resolve().parent
VAL_DIR = TOOL_DIR.parent
TBL = VAL_DIR / "tables"
EXT = TBL / "extra"


def main() -> None:
    pool_status = json.loads((TBL / "pool_status.json").read_text())
    s_core = pd.read_csv(TBL / "core_r3" / "lookup_summary.csv")
    s_knee = pd.read_csv(TBL / "knee_r3" / "lookup_summary.csv")
    s_supp = pd.read_csv(TBL / "supp_maxr" / "lookup_summary.csv")
    reps_supp = pd.read_csv(TBL / "supp_maxr" / "lookup_replications.csv")
    bm_supp = pd.read_csv(TBL / "supp_maxr" / "bottleneck_migration.csv")
    dd_supp = pd.read_csv(TBL / "supp_maxr" / "lookup_domain_delay.csv")

    rm = pd.read_csv(EXT / "run_metrics_full.csv")
    mac = pd.read_csv(EXT / "run_mac_phy_stats.csv")
    mr = pd.read_csv(EXT / "multirate_summary.csv")
    st = pd.read_csv(EXT / "staleness_summary.csv")
    dc = pd.read_csv(EXT / "drop_cause_and_tail_summary.csv")
    conf = pd.read_csv(EXT / "conformance_map.csv")
    g8b = pd.read_csv(EXT / "g8b_loo_error.csv")
    cb_sum = pd.read_csv(EXT / "collapse_b_summary.csv")
    cb_seed = pd.read_csv(EXT / "collapse_b_per_seed.csv")
    pilot = pd.read_csv(VAL_DIR / "pilot_codesign" / "codesign_summary.csv")

    print("=" * 72)
    print("1. POOL DECOMPOSITION & GLOBAL PACKET CONSERVATION (FROZEN ARCHIVE)")
    print("=" * 72)
    print("pool_status core:", pool_status["core_r3"]["complete_slices"], pool_status["core_r3"]["files"])
    print("pool_status knee:", pool_status["knee_r3"]["complete_slices"], pool_status["knee_r3"]["files"])
    print("pool_status supp:", pool_status["supp_maxr"]["complete_slices"], pool_status["supp_maxr"]["files"])
    overlap = int((mac["in_core_r3"] & mac["in_knee_r3"]).sum())
    union_r3 = int((mac["in_core_r3"] | mac["in_knee_r3"]).sum())
    base_r3_all80 = int((mac["rep"] < 3).sum())
    supp_extra_reps = int((mac["in_supp_maxr"] & (mac["rep"] >= 3)).sum())
    print(f"Total unique frozen runs: {len(mac)} (series={len(rm)})")
    print(f"  in_core_r3={int(mac['in_core_r3'].sum())}, in_knee_r3={int(mac['in_knee_r3'].sum())}, overlap={overlap}, core_union_knee={union_r3}")
    print(f"  base R=3 across all 80 pts (rep<3): {base_r3_all80}; extra paired reps (rep>=3) in supp_maxr: {supp_extra_reps}")
    print(f"  in_supp_maxr={int(mac['in_supp_maxr'].sum())}, is_collapse_extra={int(mac['is_collapse_extra'].sum())}, is_unpaired_extra={int(mac['is_unpaired_extra'].sum())}")
    # Slice breakdown of R counts in supp_maxr
    s_reps = pool_status["supp_maxr"]["slice_reps"]
    from collections import Counter
    print("  supp_maxr slice rep distribution:", dict(sorted(Counter(s_reps.values()).items())))
    for rv in sorted(set(s_reps.values())):
        if rv != 3:
            names = [k for k, v in sorted(s_reps.items()) if v == rv]
            print(f"    R={rv} ({len(names)} slices):", names[:6], ("..." if len(names) > 6 else ""))

    # Integer conservation ledger across ALL rm rows and across supp_maxr only
    for label, sub in [("ALL_5279", rm), ("SUPP_MAXR_5256", rm[rm["in_supp_maxr"]])]:
        ng = int(sub["n_generated_valid"].sum())
        nd = int(sub["n_delivered_valid"].sum())
        dq = int(sub["n_drop_queue"].sum())
        dr = int(sub["n_drop_retry"].sum())
        do = int(sub["n_drop_other"].sum())
        lt = int(sub["n_late_termination"].sum())
        diff = ng - (nd + dq + dr + do + lt)
        print(f"  Conservation [{label}]: series={len(sub)}, gen={ng:,}, deliv={nd:,}, dq={dq:,}, dr={dr:,}, do={do:,}, lt={lt:,}, diff={diff}")

    print("\n2. TAIL SAMPLE ADEQUACY (supp_maxr, 1920 series)")
    print("  flag_p99:", s_supp["flag_p99"].value_counts().to_dict())
    print("  flag_p99 by class (flagged):", s_supp[s_supp["flag_p99"] != "OK"]["class"].value_counts().to_dict())
    print("  flag_p99_9:", s_supp["flag_p99_9"].value_counts().to_dict())
    bench_pts = [(40, 54, 149.3), (80, 12, 22.4), (80, 12, 149.3)]
    b_flags = []
    for n, p, l in bench_pts:
        sub = s_supp[(s_supp["N_AMR"] == n) & (s_supp["phy_rate_Mbps"] == p) & np.isclose(s_supp["lambda_tel_Mbps"], l, atol=0.1) & (s_supp["class"] != "telemetry")]
        b_flags.append(int((sub["flag_p99"] != "OK").sum()))
    print("  Benchmark p99 flags (should be 0/54 across 3 pts x 3 crit x 6 cells):", sum(b_flags), "of", 54)

    print("\n" + "=" * 72)
    print("3. TABLE: tab:aggregate_performance (core_r3 & supp_maxr 80 pts)")
    print("=" * 72)
    nom_d = {"dds": 5, "state": 50, "orders": 50, "telemetry": 100}
    for cls in ["dds", "state", "orders", "telemetry"]:
        col = f"miss_B_{nom_d[cls]}ms"
        print(f"--- Class: {cls} (D={nom_d[cls]} ms) ---")
        for c in range(1, 7):
            sc = s_core[(s_core["class"] == cls) & (s_core["cell"] == c)]
            ss = s_supp[(s_supp["class"] == cls) & (s_supp["cell"] == c)]
            print(
                f"  C{c}: core[missB={100*sc[col].mean():.2f}, ploss={100*sc['p_loss'].mean():.2f}] | "
                f"supp80[missB={100*ss[col].mean():.2f}, ploss={100*ss['p_loss'].mean():.2f}, "
                f"max={100*ss[col].max():.2f}, >1%={int((ss[col] > 0.01).sum())}/80, "
                f"p99_mean={ss['lat_p99'].mean():.2f}, p99_max={ss['lat_p99'].max():.2f}]"
            )

    print("\n" + "=" * 72)
    print("4. TABLE: tab:deadline_spectrum (core_r3 check)")
    print("=" * 72)
    for cls in ["dds", "state", "orders", "telemetry"]:
        print(f"  Class: {cls}")
        for c in range(1, 7):
            sc = s_core[(s_core["class"] == cls) & (s_core["cell"] == c)]
            vals = [100 * sc[f"miss_B_{d}ms"].mean() for d in (1, 2, 5, 10, 20, 50, 100)] + [100 * sc["p_loss"].mean()]
            print(f"    C{c}: " + "  ".join(f"{v:.2f}" for v in vals))

    print("\n" + "=" * 72)
    print("5. RQ-1 KEY SLICES (80, 54M, 149.3M; N=5..80 at 95M; N=40 & N=80 at 12M)")
    print("=" * 72)
    # FIFO bracket at 85M vs 95M
    for lam in (85.0, 95.0, 149.3):
        sub = s_supp[(s_supp["cell"] == 1) & (s_supp["class"] == "dds") & np.isclose(s_supp["lambda_tel_Mbps"], lam, atol=0.1) & (s_supp["phy_rate_Mbps"] == 54)]
        print(f"  C1 DDS 54M {lam}M by N_AMR:", {int(r.N_AMR): round(100 * r.miss_B_5ms, 2) for _, r in sub.sort_values("N_AMR").iterrows()})
    # (80, 54M, 149.3M) C1 & C3
    for c in (1, 3, 5):
        sub = s_supp[(s_supp["cell"] == c) & (s_supp["N_AMR"] == 80) & (s_supp["phy_rate_Mbps"] == 54) & np.isclose(s_supp["lambda_tel_Mbps"], 149.3, atol=0.1)]
        print(f"  (80,54M,149.3M) C{c}:", {r["class"]: (round(100*r["miss_B_"+str(nom_d[r["class"]])+"ms"], 2), round(100*r["p_loss"], 2)) for _, r in sub.iterrows()})
    # (N=40, 12M) 8-load Orders & State (C1/C3/C5 vs C2/C4/C6)
    sub40 = s_supp[(s_supp["N_AMR"] == 40) & (s_supp["phy_rate_Mbps"] == 12)]
    for cls in ("orders", "state"):
        col = f"miss_B_{nom_d[cls]}ms"
        for c in (1, 2, 3, 4, 5, 6):
            d = sub40[(sub40["cell"] == c) & (sub40["class"] == cls)]
            print(f"  (40,12M) {cls} C{c}: min={100*d[col].min():.2f}, max={100*d[col].max():.2f}, mean={100*d[col].mean():.2f}, max_p99={d['lat_p99'].max():.2f}")
    d_w40 = (
        sub40[(sub40["cell"] == 1) & (sub40["class"] == "orders")].set_index("lambda_tel_Mbps")["miss_B_50ms"]
        - sub40[(sub40["cell"] == 2) & (sub40["class"] == "orders")].set_index("lambda_tel_Mbps")["miss_B_50ms"]
    )
    print(f"  (40,12M) 8-load Orders Delta_W mean={100*d_w40.mean():+.2f} pp, per load={ {k: round(100*v,2) for k,v in d_w40.items()} }")
    # (N=80, 12M) 8-load Orders & State
    sub80 = s_supp[(s_supp["N_AMR"] == 80) & (s_supp["phy_rate_Mbps"] == 12)]
    for cls in ("orders", "state"):
        col = f"miss_B_{nom_d[cls]}ms"
        for c in (1, 2, 3, 4, 5, 6):
            d = sub80[(sub80["cell"] == c) & (sub80["class"] == cls)]
            print(f"  (80,12M) {cls} C{c}: min={100*d[col].min():.2f}, max={100*d[col].max():.2f}, p_loss=[{100*d['p_loss'].min():.2f},{100*d['p_loss'].max():.2f}]")

    print("\n" + "=" * 72)
    print("6. TABLE: tab:domain_delay_decomp (supp_maxr 80-pt means + 5256-run ledger)")
    print("=" * 72)
    # Scenario means pooled across replications = mean over 80 points of packet-weighted point means from dd_supp (or dc_supp mean!)
    # Check how original table computed it: dd_supp grouped by [cell, class, N_AMR, lam, phy, domain] -> packet-weighted mean across reps, then mean across 80 pts!
    pt_dom = (
        dd_supp.assign(wx=dd_supp["mean_ms"] * dd_supp["n_samples"])
        .groupby(["cell", "class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps", "domain"], as_index=False)[["wx", "n_samples"]]
        .sum()
    )
    pt_dom["pt_mean"] = np.where(pt_dom["n_samples"] > 0, pt_dom["wx"] / pt_dom["n_samples"], 0.0)
    dom_means = pt_dom.groupby(["cell", "class", "domain"])["pt_mean"].mean().unstack("domain")
    for cls in ["dds", "state", "orders", "telemetry"]:
        print(f"  Class: {cls}")
        for c in range(1, 7):
            ss = s_supp[(s_supp["class"] == cls) & (s_supp["cell"] == c)]
            wl = dom_means.loc[(c, cls), "wireless"]
            sw = dom_means.loc[(c, cls), "wired_switch"]
            ws = dom_means.loc[(c, cls), "wire_serialization"]
            dq = int(ss["n_Drop_Queue"].sum())
            dr = int(ss["n_Drop_Retry"].sum())
            lt = int(ss["n_Late_Termination"].sum())
            pl = 100.0 * float(ss["p_loss"].mean())
            print(f"    C{c}: wl={wl:.3f}, sw={sw:.3f}, ws={ws:.3f}, ploss={pl:.2f}%, n_drop_Q={dq:,}, n_drop_R={dr:,}, n_late={lt:,}")
    # Also check per-AMR orders late spread at (80, 12M, 22.4M)
    dc80 = dc[(dc["pool"] == "supp_maxr") & (dc["class"] == "orders") & (dc["N_AMR"] == 80) & (dc["phy_rate_Mbps"] == 12) & np.isclose(dc["lambda_tel_Mbps"], 22.4, atol=0.1)]
    for _, r in dc80.sort_values("cell").iterrows():
        print(f"  Per-AMR Orders (80,12M,22.4M) C{int(r.cell)}: min={100*r.orders_amr_late_frac_min_mean:.2f}%, max={100*r.orders_amr_late_frac_max_mean:.2f}%")

    print("\n" + "=" * 72)
    print("7. BENCHMARK POINTS (tab:selected_points & tab:dual_stress_matrix, ALL R=22)")
    print("=" * 72)
    for label, n, p, l in [("WiredStress", 40, 54, 149.3), ("WirelessStress", 80, 12, 22.4), ("DualStress", 80, 12, 149.3)]:
        print(f"--- {label} ({n}, {p}M, {l}M) ---")
        sub = s_supp[(s_supp["N_AMR"] == n) & (s_supp["phy_rate_Mbps"] == p) & np.isclose(s_supp["lambda_tel_Mbps"], l, atol=0.1)]
        sub_dom = pt_dom[(pt_dom["N_AMR"] == n) & (pt_dom["phy_rate_Mbps"] == p) & np.isclose(pt_dom["lambda_tel_Mbps"], l, atol=0.1)]
        for cls in ["dds", "state", "orders", "telemetry"]:
            if label == "WiredStress" and cls == "orders":
                continue
            if label in ("WirelessStress", "DualStress") and cls == "dds" and label == "WirelessStress":
                pass
            col = f"miss_B_{nom_d[cls]}ms"
            for c in range(1, 7):
                r = sub[(sub["class"] == cls) & (sub["cell"] == c)].iloc[0]
                ntot = float(r["n_total"])
                q_pct = 100.0 * float(r["n_Drop_Queue"]) / ntot
                r_pct = 100.0 * float(r["n_Drop_Retry"]) / ntot
                in_fl = 100.0 * float(r["n_Late_Termination"]) / ntot
                mb = 100.0 * float(r[col])
                pl = 100.0 * float(r["p_loss"])
                late_deliv = mb - pl - in_fl
                wl = float(sub_dom[(sub_dom["class"] == cls) & (sub_dom["cell"] == c) & (sub_dom["domain"] == "wireless")]["pt_mean"].iloc[0])
                sw = float(sub_dom[(sub_dom["class"] == cls) & (sub_dom["cell"] == c) & (sub_dom["domain"] == "wired_switch")]["pt_mean"].iloc[0])
                print(
                    f"  {cls:9s} C{c} (R={int(r['n_reps'])}): missB={mb:.2f}, ploss={pl:.2f}, Q={q_pct:.2f}, R={r_pct:.2f}, "
                    f"LateDeliv={late_deliv:.2f}, InFl={in_fl:.2f}, wl={wl:.2f}, sw={sw:.2f}, p50={r['lat_p50']:.2f}, p99={r['lat_p99']:.2f}"
                )

    print("\n" + "=" * 72)
    print("8. HYPOTHESIS TEST (tab:hypothesis_test + all 240 critical pairs)")
    print("=" * 72)
    dc_s = dc[dc["pool"] == "supp_maxr"].copy()
    # Compute predicted & observed on ALL 80 pts x 3 critical classes = 240 pairs
    crit = s_supp[s_supp["class"].isin(["dds", "state", "orders"])].copy()
    # Build dict for quick lookup
    s_map = {}
    for _, r in crit.iterrows():
        s_map[(int(r.cell), str(r["class"]), int(r.N_AMR), round(float(r.lambda_tel_Mbps), 1), int(r.phy_rate_Mbps))] = r
    dom_map = {}
    for _, r in pt_dom.iterrows():
        dom_map[(int(r.cell), str(r["class"]), int(r.N_AMR), round(float(r.lambda_tel_Mbps), 1), int(r.phy_rate_Mbps), str(r.domain))] = float(r.pt_mean)

    wired_viols = []
    wl_viols = []
    hyp_rows = []
    for cls in ("dds", "state", "orders"):
        col = f"miss_B_{nom_d[cls]}ms"
        pts = sorted({(int(r.N_AMR), int(r.phy_rate_Mbps), round(float(r.lambda_tel_Mbps), 1)) for _, r in crit[crit["class"] == cls].iterrows()})
        for n, p, l in pts:
            r1 = s_map[(1, cls, n, l, p)]
            r2 = s_map[(2, cls, n, l, p)]
            r3 = s_map[(3, cls, n, l, p)]
            nt1 = float(r1["n_total"])
            mb1 = 100.0 * float(r1[col])
            pl1 = 100.0 * float(r1["p_loss"])
            late1 = mb1 - pl1  # includes in_fl which is also ~0 except collapsed/wireless
            # Split baseline loss into wired (p_drop_Q on eth[0] for DDS; for State need Queue vs Retry: Wait - State in C1 can drop at switch OR AP/AMR! Let's check Cell 3 Q drops vs Cell 1 Q drops!)
            dq1 = 100.0 * float(r1["n_Drop_Queue"]) / nt1
            dr1 = 100.0 * float(r1["n_Drop_Retry"]) / nt1
            # Wait: check how the original table attributed baseline loss to wired vs wireless!
            # In Cell 1 DDS: 100% wired. Orders: 100% wireless (never hits eth[0]). State: Cell 1 switch Q drops vs wireless retry + AMR Q drops (compare with Cell 3? Or if l >= 95M, switch Q is wired!).
            wl_m = dom_map[(1, cls, n, l, p, "wireless")]
            sw_m = dom_map[(1, cls, n, l, p, "wired_switch")]
            ws_m = dom_map[(1, cls, n, l, p, "wire_serialization")]
            tot_m = wl_m + sw_m + ws_m
            s_tau_wd = 100.0 * (sw_m / tot_m) if tot_m > 0 else 0.0
            s_tau_wl = 100.0 * (wl_m / tot_m) if tot_m > 0 else 0.0
            # Wired queue drops attributable to eth[0]: total Q drops minus wireless Q drops (measured directly from Cell 3!)
            dq3 = 100.0 * float(r3["n_Drop_Queue"]) / float(r3["n_total"])
            p_wd = 0.0 if cls == "orders" else max(0.0, dq1 - dq3)
            p_wl = pl1 - p_wd
            # Note: C1 late1 = miss_B^(1) - p_loss^(1); wait original eq says p_drop_wd^(1) + s_tau_wd^(1)*(missB^(1) - p_loss^(1))
            pred_p = p_wd + (s_tau_wd / 100.0) * (mb1 - pl1)
            pred_w = p_wl + (s_tau_wl / 100.0) * (mb1 - pl1)
            obs_p = mb1 - 100.0 * float(r3[col])
            obs_w = mb1 - 100.0 * float(r2[col])
            if obs_p - pred_p > 0.05:
                wired_viols.append((cls, n, p, l, pred_p, obs_p))
            if obs_w - pred_w > 0.05:
                wl_viols.append((cls, n, p, l, pred_w, obs_w))
            if (n, p, l, cls) in {
                (40, 54, 149.3, "dds"), (40, 54, 149.3, "state"),
                (80, 54, 149.3, "dds"), (80, 54, 149.3, "state"),
                (40, 12, 22.4, "orders"), (40, 12, 22.4, "state"),
                (80, 12, 22.4, "orders"), (80, 12, 22.4, "state"),
                (80, 12, 95.0, "state"),
                (80, 12, 149.3, "dds"), (80, 12, 149.3, "orders"), (80, 12, 149.3, "state"),
            }:
                sL_wd = 100.0 * p_wd / pl1 if pl1 > 0 else 0.0
                sL_wl = 100.0 * p_wl / pl1 if pl1 > 0 else 0.0
                hyp_rows.append((n, p, l, cls, mb1, s_tau_wd, sL_wd, s_tau_wl, sL_wl, pred_p, obs_p, pred_w, obs_w, 100*float(r3[col])))
    print(f"  Total pairs checked: {len(crit)//6}; wired viol (>0.05 pp): {len(wired_viols)} {wired_viols[:3]}")
    print(f"  Wireless slight deviations (>0.05 pp): {len(wl_viols)}, max={(max((x[5]-x[4]) for x in wl_viols) if wl_viols else 0):.2f} pp")
    # Also check max positive wireless deviation where pred_w ~= 0:
    small_w = [x for x in wl_viols if x[4] < 0.05]
    print(f"  Wireless deviations above ~0 bound: {len(small_w)}, max={max((x[5]-x[4] for x in small_w), default=0):.2f} pp")
    for hr in sorted(hyp_rows):
        n, p, l, cls, mb1, stw, slw, stl, sll, pp, op, pw, ow, c3v = hr
        cap_p = f"{100*op/pp:.1f}%" if pp > 0.5 else "-"
        cap_w = f"{100*ow/pw:.1f}%" if pw > 0.5 else "-"
        print(f"  ({n:2d},{p:2d}M,{l:5.1f}M) {cls:6s}: C1={mb1:5.2f} | Wd={stw:5.1f}/{slw:5.1f} Wl={stl:5.1f}/{sll:5.1f} | dP={pp:5.2f}/{op:+6.2f} ({cap_p}) | dW={pw:5.2f}/{ow:+6.2f} ({cap_w}) | C3={c3v:.2f}")
    # Also check Orders (80, 12M) across all 8 loads for capture ratio range
    ord80_12 = []
    for _, br in bm_supp[(bm_supp["class"] == "orders") & (bm_supp["N_AMR"] == 80) & (bm_supp["phy_rate_Mbps"] == 12)].iterrows():
        l = round(float(br.lambda_tel_Mbps), 1)
        r1 = s_map[(1, "orders", 80, l, 12)]
        r2 = s_map[(2, "orders", 80, l, 12)]
        obs_w = 100.0 * (float(r1["miss_B_50ms"]) - float(r2["miss_B_50ms"]))
        pred_w = 100.0 * float(r1["miss_B_50ms"])  # wire share is ~0.04%
        wl_m = dom_map[(1, "orders", 80, l, 12, "wireless")]
        tot_m = wl_m + dom_map[(1, "orders", 80, l, 12, "wired_switch")] + dom_map[(1, "orders", 80, l, 12, "wire_serialization")]
        pred_w2 = 100.0 * float(r1["p_loss"]) + (wl_m / tot_m) * 100.0 * (float(r1["miss_B_50ms"]) - float(r1["p_loss"]))
        ord80_12.append((l, round(obs_w, 2), round(pred_w2, 2), round(100 * obs_w / pred_w2, 1)))
    print("  Orders (80,12M) all 8 loads (lam, obs_w, pred_w, capture%):", ord80_12)

    print("\n" + "=" * 72)
    print("9. BOTTLENECK MIGRATION REGIMES (tab:migration_regimes, 320 pairs)")
    print("=" * 72)
    print("  dominant_bottleneck x class:")
    print(pd.crosstab(bm_supp["dominant_bottleneck"], bm_supp["class"], margins=True))
    # Also compute TAS shaping penalty count (telemetry with lambda_tel >= 45.0)
    tas_tel = bm_supp[(bm_supp["class"] == "telemetry") & (bm_supp["lambda_tel_Mbps"] >= 44.8)]
    print(f"  Telemetry active TAS shaping penalty (lam >= 44.8M): {len(tas_tel)}/80, mean Delta_S={100*tas_tel['wired_priority_to_tas_gain'].mean():.2f} pp")
    uncong = bm_supp[bm_supp["dominant_bottleneck"] == "none_or_uncongested"]
    print(f"  Uncongested: {len(uncong)}/{len(bm_supp)}, by class={uncong['class'].value_counts().to_dict()}")
    wired_b = bm_supp[bm_supp["dominant_bottleneck"] == "wired"]
    for cls in ("dds", "state"):
        sub = wired_b[wired_b["class"] == cls]
        print(f"  Wired bottleneck ({cls}, n={len(sub)}): mean Delta_P={100*sub['wired_fifo_to_priority_gain'].mean():+.2f} pp")
    print("  All active wired FIFO bottleneck (dds+state) with Delta_P > 1pp?:")
    spill = bm_supp[bm_supp["dominant_bottleneck"] == "scheduled_radio_penalty"]
    print(f"  AP-Block Spillover (n={len(spill)}): by class={spill['class'].value_counts().to_dict()}, mean Delta_W={100*spill['wireless_gain'].mean():.2f} pp")
    struct = bm_supp[bm_supp["dominant_bottleneck"] == "structural_schedule_wait"]
    print(f"  Structural TDMA Wait (n={len(struct)}): by class={struct['class'].value_counts().to_dict()}")
    for cls in ("orders", "state"):
        sub = struct[struct["class"] == cls]
        print(f"    {cls}: mean Delta_W={100*sub['wireless_gain'].mean():+.2f}, mean Delta_P={100*sub['wired_fifo_to_priority_gain'].mean():+.2f}")
    mixed = bm_supp[bm_supp["dominant_bottleneck"] == "mixed_or_uncertain"]
    print(f"  Mixed/Uncertain (n={len(mixed)}): by class={mixed['class'].value_counts().to_dict()}, Delta_P={100*mixed['wired_fifo_to_priority_gain'].mean():+.2f}, Delta_W={100*mixed['wireless_gain'].mean():+.2f}")
    # Also compute true Telemetry-excluding bottleneck regime partition if TAS moves out of uncongested!
    # Wait: let's print telemetry dominant_bottleneck breakdown AND wired_tas_penalty_flag breakdown
    print("  Telemetry dominant_bottleneck breakdown:", bm_supp[bm_supp["class"] == "telemetry"]["dominant_bottleneck"].value_counts().to_dict())
    print("  Telemetry wired_tas_penalty_flag breakdown:", bm_supp[bm_supp["class"] == "telemetry"]["wired_tas_penalty_flag"].value_counts().to_dict())
    # Notice: in old report, Telemetry had 10 uncongested (64 pts - 54 TAS penalty pts!) and 54 Wired TAS shaping penalty!
    # With 80 pts: how many Telemetry pts have lam < 44.8 vs lam >= 44.8?
    print("  Telemetry lam < 44.8 count:", int((bm_supp[bm_supp["class"] == "telemetry"]["lambda_tel_Mbps"] < 44.8).sum()), "of 80")

    print("\n" + "=" * 72)
    print("10. CONFORMANCE SUMMARY (tab:conformance_summary, supp_maxr 80 pts)")
    print("=" * 72)
    cs = conf[conf["pool"] == "supp_maxr"]
    crit_sub = cs[cs["class"].isin(["dds", "state", "orders"])]
    piv = crit_sub.pivot_table(index=["cell", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"], columns="class", values="state", aggfunc="first")
    def _joint3(row):
        vals = {row["dds"], row["state"], row["orders"]}
        if "violates" in vals:
            return "violates"
        if vals == {"conforms"}:
            return "conforms"
        return "unresolved"
    piv["joint3"] = piv.apply(_joint3, axis=1)
    j4 = cs.drop_duplicates(["cell", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"])
    for c in range(1, 7):
        parts = []
        for cls in ("dds", "state", "orders", "telemetry"):
            sub = cs[(cs["cell"] == c) & (cs["class"] == cls)]
            vc = sub["state"].value_counts().to_dict()
            parts.append(f"{cls}={vc.get('conforms',0)}/{vc.get('unresolved',0)}/{vc.get('violates',0)}")
        j3c = piv.loc[c]["joint3"].value_counts().to_dict()
        j4c = j4[j4["cell"] == c]["joint_4class_state"].value_counts().to_dict()
        npts = len(j4[j4["cell"] == c])
        print(
            f"  C{c}: " + " | ".join(parts) +
            f" | J3={j3c.get('conforms',0)}/{j3c.get('unresolved',0)}/{j3c.get('violates',0)} ({100*j3c.get('conforms',0)/npts:.1f}%)" +
            f" | J4={j4c.get('conforms',0)}/{j4c.get('unresolved',0)}/{j4c.get('violates',0)} ({100*j4c.get('conforms',0)/npts:.1f}%)"
        )

    print("\n" + "=" * 72)
    print("11. SUPPORTING DIAGNOSTICS, MULTIRATE NER & STALENESS, G8b LOO, PILOT")
    print("=" * 72)
    # TDMA run counts & AP grant releases in supp_maxr
    m_supp = mac[mac["in_supp_maxr"]]
    tdma = m_supp[m_supp["cell"].isin([2, 4, 6])]
    print(f"  TDMA supp_maxr total runs: {len(tdma)} -> C2={int((tdma['cell']==2).sum())}, C4={int((tdma['cell']==4).sum())}, C6={int((tdma['cell']==6).sum())}")
    for c in (2, 4, 6):
        t_c = tdma[tdma["cell"] == c]
        print(
            f"    C{c}: amr_retry_drops={t_c['amr_retry_limit_drops_sum'].sum():.0f}, "
            f"ap_grant_released={t_c['ap_sched_grant_released'].sum():.0f}, "
            f"amr_grant_released={t_c['amr_sched_grant_released_sum'].sum():.0f}"
        )
    # Multi-rate NER & ZOH staleness (tab:ner_multirate)
    for pool_name, grp_specs in [
        ("core_r3", [("dds", [1, 2])]),
        ("supp_maxr", [("dds", [1, 2]), ("dds", [3, 4, 5, 6]), ("state", [1]), ("state", [2]), ("state", [3]), ("state", [5]), ("state", [4, 6]), ("orders", [1, 3, 5]), ("orders", [2, 4, 6])]),
    ]:
        print(f"  --- Multirate [{pool_name}] ---")
        mr_p = mr[mr["pool"] == pool_name]
        st_p = st[st["pool"] == pool_name]
        dc_p = dc[dc["pool"] == pool_name]
        for cls, clist in grp_specs:
            m_sub = mr_p[(mr_p["class"] == cls) & (mr_p["cell"].isin(clist))]
            s_sub = st_p[(st_p["class"] == cls) & (st_p["cell"].isin(clist))]
            d_sub = dc_p[(dc_p["class"] == cls) & (dc_p["cell"].isin(clist))]
            ttl_mean = 100.0 * float(s_sub["p_late_ttl_of_generated"].mean())
            ttl_max = 100.0 * float(s_sub["p_late_ttl_of_generated"].max())
            # pooled ZOH staleness mean across scenario-level vs sample-weighted
            z_mean_w = float((s_sub["stale10_mean"] * s_sub["stale10_samples"]).sum() / max(1.0, s_sub["stale10_samples"].sum()))
            z_max = float(s_sub["stale10_max"].max())
            z50_max = float(s_sub["stale50_max"].max())
            z500_max = float(s_sub["stale500_max"].max())
            print(
                f"    {cls:6s} C{clist}: missA={100*m_sub['miss_A_nom'].mean():.2f}, "
                f"B10={100*m_sub['miss_B_nom_T10ms'].mean():.2f}, B50={100*m_sub['miss_B_nom_T50ms'].mean():.2f}, "
                f"B500={100*m_sub['miss_B_nom_T500ms'].mean():.2f}, BT={100*m_sub['miss_BT_L_eq_T10ms'].mean():.2f} | "
                f"TTL={ttl_mean:.2f}/{ttl_max:.1f}% | ZOH10={z_mean_w:.2f}/{z_max:.0f}t (50:{z50_max:.0f}, 500:{z500_max:.0f})"
            )
    # Check staleness <= 40 check for Fig 9B
    st_n40 = st[(st["pool"] == "supp_maxr") & (st["class"] == "state") & (st["N_AMR"] <= 40) & (st["phy_rate_Mbps"] == 12) & np.isclose(st["lambda_tel_Mbps"], 22.4, atol=0.1)]
    print("  Staleness <=40 at (12M,22.4M) max mean/max:", float(st_n40["stale10_mean"].max()), float(st_n40["stale10_max"].max()))

    # G8b LOO verify
    print("  --- G8b Matched 4-load vs 8-load (N in {10,20,40}, held in {74.7,95.0}) ---")
    m_g8 = g8b[(g8b["mode"] == "lo_lambda_o") & (g8b["N_AMR"].isin([10, 20, 40])) & (g8b["held_value"].isin([74.7, 95.0]))]
    for cls in ("dds", "state", "telemetry", "orders"):
        c4 = m_g8[(m_g8["pool"] == "core_r3") & (m_g8["class"] == cls)]
        c8 = m_g8[(m_g8["pool"] == "knee_r3") & (m_g8["class"] == cls)]
        dw1 = 100.0 * (c8["w1_ms"].mean() - c4["w1_ms"].mean()) / c4["w1_ms"].mean()
        dmb = 100.0 * (c8["abs_err_miss_B_nom"].mean() - c4["abs_err_miss_B_nom"].mean()) / c4["abs_err_miss_B_nom"].mean()
        print(f"    {cls:9s} (n={len(c4)}): W1 {c4['w1_ms'].mean():.3f}->{c8['w1_ms'].mean():.3f} ({dw1:+.1f}%), p99 {c4['abs_err_p99_ms'].mean():.3f}->{c8['abs_err_p99_ms'].mean():.3f}, missB {100*c4['abs_err_miss_B_nom'].mean():.2f}->{100*c8['abs_err_miss_B_nom'].mean():.2f} ({dmb:+.1f}%)")
    print("  --- G8b Full Axes ---")
    for (pool, mode, cls), grp in g8b.groupby(["pool", "mode", "class"]):
        print(
            f"    {cls:9s} {pool:7s} {mode:11s} n={len(grp):3d}: "
            f"ploss={100*grp['abs_err_p_loss'].mean():.2f}, missB={100*grp['abs_err_miss_B_nom'].mean():.2f}, "
            f"p50={grp['abs_err_p50_ms'].mean():.3f}, p99={grp['abs_err_p99_ms'].mean():.3f}, "
            f"W1={grp['w1_ms'].mean():.3f}/{grp['w1_ms'].median():.3f}"
        )

    # Check Cell 4 baseline at (40, 12M, 22.4M) & (80, 12M, 22.4M) in supp_maxr R=22 vs pilot
    print("  --- Cell 4 co-design vs R=22 supp_maxr ---")
    for n in (40, 80):
        for cls in ("orders", "state"):
            r4 = s_supp[(s_supp["cell"] == 4) & (s_supp["class"] == cls) & (s_supp["N_AMR"] == n) & (s_supp["phy_rate_Mbps"] == 12) & np.isclose(s_supp["lambda_tel_Mbps"], 22.4, atol=0.1)].iloc[0]
            p_r = pilot[(pilot["N_AMR"] == n) & (pilot["class"] == cls)].iloc[0]
            print(
                f"    N={n} {cls:6s}: supp(R={int(r4.n_reps)}) missB={100*r4['miss_B_50ms']:.2f}%, p99={r4['lat_p99']:.2f}ms | "
                f"pilot missB={p_r['pilot_miss_B_50_pct']:.2f}%, p50/p95/p99={p_r['pilot_p50_ms']:.2f}/{p_r['pilot_p95_ms']:.2f}/{p_r['pilot_p99_ms']:.2f}ms"
            )
    # Collapse incidence check
    print("  --- Collapse B ---")
    print(cb_sum.to_string(index=False))
    print("  Intermediates (rep, state_miss_B_50ms):", [(int(r.rep), round(100*r.state_miss_B_50ms, 2)) for _, r in cb_seed[cb_seed["regime"] == "intermediate"].sort_values("state_miss_B_50ms").iterrows()])
    print("  Collapsed (rep, miss, p99):", [(int(r.rep), round(100*r.state_miss_B_50ms, 2), round(r.state_p99_ms, 1)) for _, r in cb_seed[cb_seed["regime"] == "collapsed"].iterrows()])
    print("  Normal median miss:", round(100 * float(cb_seed[cb_seed["regime"] == "normal"]["state_miss_B_50ms"].median()), 2))


if __name__ == "__main__":
    main()

