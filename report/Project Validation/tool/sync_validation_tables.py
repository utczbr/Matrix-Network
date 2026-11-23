#!/usr/bin/env python3
"""Synchronize report/Project Validation/tables/extra/ to the frozen p4_grid80_r3 snapshot.

Reads ONLY the frozen runs in report/Project Validation/tables/supp_maxr_manifest.csv (5,256 runs)
plus extra Cell 1 collapse seeds in simulations/results/collapse_B/ with rep >= 22 (23 runs;
total 5,279 unique runs), reusing cached rows from existing run_metrics_full.csv and
run_mac_phy_stats.csv where present, enforcing strict 6-bin packet conservation on every newly
parsed .sca.gz file, and regenerating:
  - run_metrics_full.csv
  - run_mac_phy_stats.csv
  - staleness_summary.csv
  - multirate_summary.csv
  - drop_cause_and_tail_summary.csv
  - mac_phy_summary.csv
Strictly writes inside git-ignored report/Project Validation/tables/extra/.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import math
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

TOOL_DIR = Path(__file__).resolve().parent
VAL_DIR = TOOL_DIR.parent
ROOT = VAL_DIR.parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "report" / "interim_20h" / "tools"))
sys.path.insert(0, str(ROOT / "report" / "interim_20h" / "preliminary_extras"))

import build_uniform_pool as bup  # noqa: E402
import deadline_metrics as dm  # noqa: E402
import export_lookup as ex  # noqa: E402
import extract_all_metrics as eam  # noqa: E402

OUT_DIR = VAL_DIR / "tables" / "extra"
SUPP_MAN_PATH = VAL_DIR / "tables" / "supp_maxr_manifest.csv"

COLLAPSE_RE = re.compile(
    r"^Cell1_Sweep-nAmr=80,nSta=4,phyRate=12Mbps,telInterval=2000us-#(?P<rep>\d+)\.sca\.gz$"
)


def _worker_parse(task: Tuple[Dict[str, object], Dict[Tuple[int, int, str], int], set, set]):
    info, paired_max, core_set, knee_set = task
    cell = int(info["cell"])
    namr = int(info["nAmr"])
    phy = int(info["phy"])
    tel = str(info["telInterval"])
    rep = int(info["rep"])
    src_name = str(info["source"])
    filename = str(info["filename"])

    if src_name == "collapse_B":
        sca_path = ROOT / "simulations" / "results" / "collapse_B" / filename
    else:
        sca_path = ROOT / "simulations" / "results" / src_name / filename
        if not sca_path.exists():
            sca_path = ROOT / "simulations" / "results" / "pools" / "supp_maxr" / filename
    if not sca_path.exists():
        raise FileNotFoundError(f"Missing .sca.gz file for {info}")

    lam = ex.TEL_INTERVAL_TO_MBPS[tel]
    sk = (namr, phy, tel)
    r_pair = paired_max.get(sk, 0)

    in_core_r3 = (sk in core_set) and (rep < 3) and (r_pair >= 3)
    in_knee_r3 = (sk in knee_set) and (rep < 3) and (r_pair >= 3)
    in_supp_maxr = rep < r_pair
    is_post_b2cfdb7 = (namr == 80 and phy == 54 and tel == "2000us" and rep >= 3)
    is_collapse_extra = (cell == 1 and namr == 80 and phy == 12 and tel == "2000us" and rep >= 22)
    is_unpaired_extra = (not in_supp_maxr) and (not is_post_b2cfdb7) and (not is_collapse_extra)

    _attrs, scalars, stats, _ = eam.parse_sca_single_pass(sca_path, parse_mob=False)
    coord_mods = [
        m for m, sname in scalars if sname == "n_generated_valid_orders" and m.endswith(".experimentCoordinator")
    ]
    if len(coord_mods) != 1:
        raise RuntimeError(f"{sca_path.name}: expected 1 coordinator, found {coord_mods}")
    cmod = coord_mods[0]

    amr_order_sinks: List[Tuple[int, str]] = []
    amr_dcf_mods: List[str] = []
    amr_rec_mods: List[str] = []
    seen_dcf = set()
    seen_rec = set()
    for (mod, sname) in scalars:
        if sname == "n_valid_delivered":
            mm = eam.AMR_SINK_RE.match(mod)
            if mm:
                amr_order_sinks.append((int(mm.group(1)), mod))
        elif (
            sname == "packetSentToPeer:count"
            and mod.startswith("MatrixFactoryNetwork.amr[")
            and mod.endswith("].wlan[0].mac.dcf")
        ):
            if mod not in seen_dcf:
                seen_dcf.add(mod)
                amr_dcf_mods.append(mod)
        elif (
            sname == "retryLimitReached:count"
            and mod.startswith("MatrixFactoryNetwork.amr[")
            and mod.endswith("].wlan[0].mac.dcf.recoveryProcedure")
        ):
            if mod not in seen_rec:
                seen_rec.add(mod)
                amr_rec_mods.append(mod)
    amr_order_sinks.sort()
    amr_dcf_mods.sort()
    amr_rec_mods.sort()

    cls_rows: List[Dict[str, object]] = []
    for cls in dm.CLASSES:
        d_nom = dm.NOMINAL_D_MS[cls]
        if cls == "orders":
            sink_mods = [m for _, m in amr_order_sinks]
        elif cls == "state":
            sink_mods = ["MatrixFactoryNetwork.fms.app[0].sink"]
        elif cls == "telemetry":
            sink_mods = ["MatrixFactoryNetwork.fms.app[1].sink"]
        else:
            sink_mods = ["MatrixFactoryNetwork.fms.app[2].sink"]

        n_rx = int(sum(scalars[(m, "n_received_total")] for m in sink_mods))
        n_wu = int(sum(scalars[(m, "n_filtered_warmup")] for m in sink_mods))
        n_hz = int(sum(scalars[(m, "n_filtered_horizon")] for m in sink_mods))
        n_deliv = int(sum(scalars[(m, "n_valid_delivered")] for m in sink_mods))
        n_dom = int(sum(scalars[(m, "n_domain_breakdown_valid")] for m in sink_mods))
        n_ttl = int(sum(scalars.get((m, "n_late_discarded_ttl"), 0.0) for m in sink_mods))

        ng = int(scalars[(cmod, f"n_generated_valid_{cls}")])
        nd_coord = int(scalars[(cmod, f"n_delivered_valid_{cls}")])
        dq = int(scalars[(cmod, f"n_drop_queue_{cls}")])
        dr = int(scalars[(cmod, f"n_drop_retry_{cls}")])
        do = int(scalars[(cmod, f"n_drop_other_{cls}")])
        lt = int(scalars[(cmod, f"n_late_termination_{cls}")])
        drops = dq + dr + do
        term_misses = drops + lt
        if not ((n_rx == n_deliv + n_wu + n_hz) and (nd_coord == n_deliv == n_dom) and (ng == n_deliv + term_misses)):
            raise RuntimeError(f"Conservation mismatch in {sca_path.name} ({cls})")

        def _rate(sname: str) -> float:
            if ng <= 0:
                return float("nan")
            return (int(sum(scalars[(m, sname)] for m in sink_mods)) + term_misses) / ng

        if cls == "orders" and sink_mods:
            amr_miss_vals = [
                scalars[(m, "n_miss_B_50ms")] / scalars[(m, "n_valid_delivered")]
                if scalars[(m, "n_valid_delivered")] > 0
                else 1.0
                for m in sink_mods
            ]
            amr_p99_vals = [scalars.get((m, "lat_p99_ms"), float("nan")) for m in sink_mods]
            amr_p99_vals = [v for v in amr_p99_vals if math.isfinite(v)]
            ord_min = float(np.min(amr_miss_vals))
            ord_p50 = float(np.median(amr_miss_vals))
            ord_max = float(np.max(amr_miss_vals))
            ord_p99_min = float(np.min(amr_p99_vals)) if amr_p99_vals else float("nan")
            ord_p99_max = float(np.max(amr_p99_vals)) if amr_p99_vals else float("nan")
        else:
            ord_min = ord_p50 = ord_max = ord_p99_min = ord_p99_max = float("nan")

        row_cls: Dict[str, object] = {
            "cell": cell,
            "class": cls,
            "N_AMR": namr,
            "lambda_tel_Mbps": lam,
            "phy_rate_Mbps": phy,
            "rep": rep,
            "source": src_name,
            "in_core_r3": in_core_r3,
            "in_knee_r3": in_knee_r3,
            "in_supp_maxr": in_supp_maxr,
            "is_post_b2cfdb7": is_post_b2cfdb7,
            "is_collapse_extra": is_collapse_extra,
            "is_unpaired_extra": is_unpaired_extra,
            "n_paired_reps_max": r_pair,
            "n_generated_valid": ng,
            "n_delivered_valid": n_deliv,
            "n_drop_queue": dq,
            "n_drop_retry": dr,
            "n_drop_other": do,
            "n_late_termination": lt,
            "n_late_discarded_ttl": n_ttl,
            "p_loss": (drops / ng) if ng else float("nan"),
            "p_drop_queue": (dq / ng) if ng else float("nan"),
            "p_drop_retry": (dr / ng) if ng else float("nan"),
            "p_drop_other": (do / ng) if ng else float("nan"),
            "p_late_termination": (lt / ng) if ng else float("nan"),
            "p_late_ttl_of_generated": (n_ttl / ng) if ng else float("nan"),
            "miss_A_nom": _rate(f"n_miss_A_{d_nom}ms"),
            "miss_B_nom_T10ms": _rate(f"n_miss_B_{d_nom}ms"),
            "miss_B_nom_T50ms": _rate(f"n_miss_B_{d_nom}ms_T50ms"),
            "miss_B_nom_T500ms": _rate(f"n_miss_B_{d_nom}ms_T500ms"),
            "miss_BT_L_eq_T10ms": _rate("n_miss_BT_L_eq_T10ms"),
            "miss_BT_L_eq_T50ms": _rate("n_miss_BT_L_eq_T50ms"),
            "miss_BT_L_eq_T500ms": _rate("n_miss_BT_L_eq_T500ms"),
            "lat_p50_ms": scalars.get((cmod, f"ecdf_{cls}_q_0.500"), float("nan")) if n_deliv else float("nan"),
            "lat_p90_ms": scalars.get((cmod, f"ecdf_{cls}_q_0.900"), float("nan")) if n_deliv else float("nan"),
            "lat_p95_ms": scalars.get((cmod, f"ecdf_{cls}_q_0.950"), float("nan")) if n_deliv else float("nan"),
            "lat_p99_ms": scalars.get((cmod, f"ecdf_{cls}_q_0.990"), float("nan")) if n_deliv else float("nan"),
            "lat_p99_9_ms": scalars.get((cmod, f"ecdf_{cls}_q_0.999"), float("nan")) if n_deliv else float("nan"),
            "orders_amr_deliv_late_frac_min": ord_min,
            "orders_amr_deliv_late_frac_p50": ord_p50,
            "orders_amr_deliv_late_frac_max": ord_max,
            "orders_amr_p99_min_ms": ord_p99_min,
            "orders_amr_p99_max_ms": ord_p99_max,
        }
        for pref, stat_name in [
            ("e2e", "e2eDelay_ms"),
            ("wireless", "wirelessDomainDelay_ms"),
            ("wired_sw", "wiredSwitchDelay_ms"),
            ("wire_ser", "wireSerializationAndPropDelay_ms"),
            ("stale10", "stalenessTicks_10ms"),
            ("stale50", "stalenessTicks_50ms"),
            ("stale500", "stalenessTicks_500ms"),
        ]:
            st_dict = eam._pool_stats([stats.get((m, stat_name), {}) for m in sink_mods])
            row_cls[f"{pref}_count"] = st_dict["count"]
            row_cls[f"{pref}_mean"] = st_dict["mean"]
            row_cls[f"{pref}_stddev"] = st_dict["stddev"]
            row_cls[f"{pref}_min"] = st_dict["min"]
            row_cls[f"{pref}_max"] = st_dict["max"]
        cls_rows.append(row_cls)

    ap_dcf = "MatrixFactoryNetwork.ap.wlan[0].mac.dcf"
    ap_rec = "MatrixFactoryNetwork.ap.wlan[0].mac.dcf.recoveryProcedure"
    ap_eth = "MatrixFactoryNetwork.ap.eth[0].mac"
    ap_tx = float(scalars.get((ap_dcf, "packetSentToPeer:count"), 0.0))
    ap_tx_ret = float(scalars.get((ap_dcf, "packetSentToPeerWithRetry:count"), 0.0))
    ap_ret_drop = float(scalars.get((ap_rec, "retryLimitReached:count"), 0.0))

    amr_tx_vals = [float(scalars.get((m, "packetSentToPeer:count"), 0.0)) for m in amr_dcf_mods]
    amr_ret_vals = [float(scalars.get((m, "packetSentToPeerWithRetry:count"), 0.0)) for m in amr_dcf_mods]
    amr_drop_vals = [float(scalars.get((m, "retryLimitReached:count"), 0.0)) for m in amr_rec_mods]
    amr_tx_sum = float(sum(amr_tx_vals))
    amr_ret_sum = float(sum(amr_ret_vals))
    amr_drop_sum = float(sum(amr_drop_vals))
    amr_drop_max = float(max(amr_drop_vals)) if amr_drop_vals else 0.0
    ap_fseq = stats.get((ap_dcf, "frameSequenceDuration:histogram"), {})
    amr_fseq = eam._pool_stats([stats.get((m, "frameSequenceDuration:histogram"), {}) for m in amr_dcf_mods])

    mac_row = {
        "cell": cell,
        "N_AMR": namr,
        "lambda_tel_Mbps": lam,
        "phy_rate_Mbps": phy,
        "rep": rep,
        "source": src_name,
        "in_core_r3": in_core_r3,
        "in_knee_r3": in_knee_r3,
        "in_supp_maxr": in_supp_maxr,
        "is_post_b2cfdb7": is_post_b2cfdb7,
        "is_collapse_extra": is_collapse_extra,
        "is_unpaired_extra": is_unpaired_extra,
        "ap_tx_pkts": ap_tx,
        "ap_tx_retry_pkts": ap_tx_ret,
        "ap_tx_retry_ratio": (ap_tx_ret / ap_tx) if ap_tx > 0 else float("nan"),
        "ap_retry_limit_drops": ap_ret_drop,
        "ap_frame_seq_mean_ms": ap_fseq.get("mean", float("nan")) * 1000.0 if "mean" in ap_fseq else float("nan"),
        "ap_frame_seq_max_ms": ap_fseq.get("max", float("nan")) * 1000.0 if "max" in ap_fseq else float("nan"),
        "amr_tx_pkts_sum": amr_tx_sum,
        "amr_tx_retry_pkts_sum": amr_ret_sum,
        "amr_tx_retry_ratio": (amr_ret_sum / amr_tx_sum) if amr_tx_sum > 0 else float("nan"),
        "amr_retry_limit_drops_sum": amr_drop_sum,
        "amr_retry_limit_drops_max": amr_drop_max,
        "amr_frame_seq_mean_ms": amr_fseq["mean"] * 1000.0 if math.isfinite(amr_fseq["mean"]) else float("nan"),
        "amr_frame_seq_max_ms": amr_fseq["max"] * 1000.0 if math.isfinite(amr_fseq["max"]) else float("nan"),
        "ap_sched_granted": float(scalars.get((ap_dcf, "scheduledDcf_numGrantedInSlot"), float("nan"))),
        "ap_sched_slot_deferrals": float(scalars.get((ap_dcf, "scheduledDcf_numSlotDeferrals"), float("nan"))),
        "ap_sched_enq_deferrals": float(scalars.get((ap_dcf, "scheduledDcf_numDeferredOnEnqueue"), float("nan"))),
        "ap_sched_grant_released": float(scalars.get((ap_dcf, "scheduledDcf_numGrantReleased"), float("nan"))),
        "amr_sched_granted_sum": (
            float(
                sum(
                    scalars[(m, "scheduledDcf_numGrantedInSlot")]
                    for m in amr_dcf_mods
                    if (m, "scheduledDcf_numGrantedInSlot") in scalars
                )
            )
            if cell in (2, 4, 6)
            else float("nan")
        ),
        "amr_sched_slot_deferrals_sum": (
            float(
                sum(
                    scalars[(m, "scheduledDcf_numSlotDeferrals")]
                    for m in amr_dcf_mods
                    if (m, "scheduledDcf_numSlotDeferrals") in scalars
                )
            )
            if cell in (2, 4, 6)
            else float("nan")
        ),
        "amr_sched_enq_deferrals_sum": (
            float(
                sum(
                    scalars[(m, "scheduledDcf_numDeferredOnEnqueue")]
                    for m in amr_dcf_mods
                    if (m, "scheduledDcf_numDeferredOnEnqueue") in scalars
                )
            )
            if cell in (2, 4, 6)
            else float("nan")
        ),
        "amr_sched_grant_released_sum": (
            float(
                sum(
                    scalars[(m, "scheduledDcf_numGrantReleased")]
                    for m in amr_dcf_mods
                    if (m, "scheduledDcf_numGrantReleased") in scalars
                )
            )
            if cell in (2, 4, 6)
            else float("nan")
        ),
        "ap_eth_rx_util_pct": float(scalars.get((ap_eth, "rx channel utilization (%)"), float("nan"))),
        "ap_eth_tx_mbps": float(scalars.get((ap_eth, "bits/sec sent"), float("nan"))) / 1e6,
        "ap_eth_rx_mbps": float(scalars.get((ap_eth, "bits/sec rcvd"), float("nan"))) / 1e6,
        "ap_eth_tx_fps": float(scalars.get((ap_eth, "frames/sec sent"), float("nan"))),
        "ap_eth_rx_fps": float(scalars.get((ap_eth, "frames/sec rcvd"), float("nan"))),
        "radio_tx_count": float(scalars.get(("MatrixFactoryNetwork.radioMedium", "transmission count"), float("nan"))),
        "radio_interference_count": float(
            scalars.get(("MatrixFactoryNetwork.radioMedium", "interference computation count"), float("nan"))
        ),
    }
    return cls_rows, mac_row


def sync_all() -> None:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    man = pd.read_csv(SUPP_MAN_PATH)
    frozen_rows: List[Dict[str, object]] = [mr.to_dict() for _, mr in man.iterrows()]
    supp_keys = {
        (int(mr.cell), int(mr.nAmr), round(ex.TEL_INTERVAL_TO_MBPS[str(mr.telInterval)], 1), int(mr.phy), int(mr.rep))
        for _, mr in man.iterrows()
    }

    collapse_dir = ROOT / "simulations" / "results" / "collapse_B"
    collapse_extra_count = 0
    if collapse_dir.exists():
        for p in sorted(collapse_dir.glob("*.sca.gz")):
            m = COLLAPSE_RE.match(p.name)
            if not m:
                continue
            rep = int(m.group("rep"))
            if rep < 22:
                continue
            k = (1, 80, 22.4, 12, rep)
            if k not in supp_keys:
                collapse_extra_count += 1
                frozen_rows.append(
                    {
                        "cell": 1,
                        "nAmr": 80,
                        "phy": 12,
                        "telInterval": "2000us",
                        "rep": rep,
                        "source": "collapse_B",
                        "filename": p.name,
                    }
                )

    frozen_key_set = {
        (int(r["cell"]), int(r["nAmr"]), round(ex.TEL_INTERVAL_TO_MBPS[str(r["telInterval"])], 1), int(r["phy"]), int(r["rep"]))
        for r in frozen_rows
    }
    assert len(frozen_key_set) == len(frozen_rows), "Duplicate keys in frozen set"

    cls_path = OUT_DIR / "run_metrics_full.csv"
    mac_path = OUT_DIR / "run_mac_phy_stats.csv"
    if cls_path.exists() and mac_path.exists():
        df_cls = pd.read_csv(cls_path)
        df_mac = pd.read_csv(mac_path)
        # Retain only cached rows belonging to the frozen target set
        cls_keys = [
            (int(c), int(n), round(float(l), 1), int(p), int(r))
            for c, n, l, p, r in zip(df_cls["cell"], df_cls["N_AMR"], df_cls["lambda_tel_Mbps"], df_cls["phy_rate_Mbps"], df_cls["rep"])
        ]
        mac_keys = [
            (int(c), int(n), round(float(l), 1), int(p), int(r))
            for c, n, l, p, r in zip(df_mac["cell"], df_mac["N_AMR"], df_mac["lambda_tel_Mbps"], df_mac["phy_rate_Mbps"], df_mac["rep"])
        ]
        df_cls = df_cls[[k in frozen_key_set for k in cls_keys]].copy()
        df_mac = df_mac[[k in frozen_key_set for k in mac_keys]].copy()
        existing_keys = {k for k in mac_keys if k in frozen_key_set}
    else:
        df_cls = pd.DataFrame()
        df_mac = pd.DataFrame()
        existing_keys = set()

    tel_rev = {round(v, 1): k for k, v in ex.TEL_INTERVAL_TO_MBPS.items() if k != "2ms"}
    core_set = {(n, p, t) for n in bup.CORE_NAMRS for p in bup.PHYS for t in bup.CORE_TELS}
    knee_set = {(n, p, t) for n in bup.KNEE_NAMRS for p in bup.PHYS for t in bup.ALL_TELS}
    all_slices = [(n, p, t) for n in bup.ALL_NAMRS for p in bup.PHYS for t in bup.ALL_TELS]

    paired_max: Dict[Tuple[int, int, str], int] = {}
    for sk in all_slices:
        namr, phy, tel = sk
        lam_r = round(ex.TEL_INTERVAL_TO_MBPS[tel], 1)
        r = 0
        while all((c, namr, lam_r, phy, r) in supp_keys for c in bup.CELLS):
            r += 1
        paired_max[sk] = r

    new_rows_info = []
    for r_info in frozen_rows:
        k = (
            int(r_info["cell"]),
            int(r_info["nAmr"]),
            round(ex.TEL_INTERVAL_TO_MBPS[str(r_info["telInterval"])], 1),
            int(r_info["phy"]),
            int(r_info["rep"]),
        )
        if k not in existing_keys:
            new_rows_info.append(r_info)

    print(
        f"[sync] Frozen target runs: {len(frozen_rows)} (supp_maxr={len(man)}, collapse_extra={collapse_extra_count}); "
        f"cached={len(existing_keys)}; to_parse={len(new_rows_info)}"
    )

    new_cls_rows: List[Dict[str, object]] = []
    new_mac_rows: List[Dict[str, object]] = []
    if new_rows_info:
        tasks = [(info, paired_max, core_set, knee_set) for info in new_rows_info]
        with ProcessPoolExecutor(max_workers=4) as pool:
            for idx_i, (c_rows, m_row) in enumerate(pool.map(_worker_parse, tasks, chunksize=16), 1):
                new_cls_rows.extend(c_rows)
                new_mac_rows.append(m_row)
                if idx_i % 500 == 0 or idx_i == len(tasks):
                    print(f"  parsed {idx_i}/{len(tasks)} new files ({time.time() - t0:.1f}s)")

        df_cls = pd.concat([df_cls, pd.DataFrame(new_cls_rows)], ignore_index=True) if not df_cls.empty else pd.DataFrame(new_cls_rows)
        df_mac = pd.concat([df_mac, pd.DataFrame(new_mac_rows)], ignore_index=True) if not df_mac.empty else pd.DataFrame(new_mac_rows)

    def _update_flags(df: pd.DataFrame, is_cls: bool) -> pd.DataFrame:
        df = df.copy()
        new_core, new_knee, new_supp, new_rmax, new_col, new_unp = [], [], [], [], [], []
        for c_v, n_v, l_v, p_v, rep_v in zip(
            df["cell"], df["N_AMR"], df["lambda_tel_Mbps"], df["phy_rate_Mbps"], df["rep"]
        ):
            tel = tel_rev[round(float(l_v), 1)]
            sk = (int(n_v), int(p_v), tel)
            r_pair = paired_max[sk]
            rep_i = int(rep_v)
            in_c = (sk in core_set) and (rep_i < 3) and (r_pair >= 3)
            in_k = (sk in knee_set) and (rep_i < 3) and (r_pair >= 3)
            in_s = rep_i < r_pair
            is_col = (int(c_v) == 1 and int(n_v) == 80 and int(p_v) == 12 and tel == "2000us" and rep_i >= 22)
            is_unp = (not in_s) and (not is_col)
            new_core.append(in_c)
            new_knee.append(in_k)
            new_supp.append(in_s)
            new_rmax.append(r_pair)
            new_col.append(is_col)
            new_unp.append(is_unp)
        df["in_core_r3"] = new_core
        df["in_knee_r3"] = new_knee
        df["in_supp_maxr"] = new_supp
        df["is_collapse_extra"] = new_col
        df["is_unpaired_extra"] = new_unp
        if is_cls:
            df["n_paired_reps_max"] = new_rmax
        return df

    df_cls = _update_flags(df_cls, is_cls=True).sort_values(
        ["N_AMR", "phy_rate_Mbps", "lambda_tel_Mbps", "cell", "class", "rep"]
    ).reset_index(drop=True)
    df_mac = _update_flags(df_mac, is_cls=False).sort_values(
        ["N_AMR", "phy_rate_Mbps", "lambda_tel_Mbps", "cell", "rep"]
    ).reset_index(drop=True)

    assert len(df_mac) == len(frozen_rows), f"Expected {len(frozen_rows)} runs, got {len(df_mac)}"
    assert int(df_mac["in_supp_maxr"].sum()) == len(man), f"Expected {len(man)} supp_maxr runs, got {int(df_mac['in_supp_maxr'].sum())}"
    assert int(df_mac["in_core_r3"].sum()) == 720, f"Expected 720 core_r3 runs, got {int(df_mac['in_core_r3'].sum())}"
    assert int(df_mac["in_knee_r3"].sum()) == 864, f"Expected 864 knee_r3 runs, got {int(df_mac['in_knee_r3'].sum())}"
    assert len(df_cls) == len(frozen_rows) * 4, f"Expected {len(frozen_rows) * 4} class rows, got {len(df_cls)}"

    df_cls.to_csv(OUT_DIR / "run_metrics_full.csv", index=False)
    df_mac.to_csv(OUT_DIR / "run_mac_phy_stats.csv", index=False)

    # Reconstruct additive (sum, sqrsum) from (count, mean, stddev) for pooling
    df_pool = df_cls.copy()
    for pref in ("e2e", "wireless", "wired_sw", "wire_ser", "stale10", "stale50", "stale500"):
        cnt = df_pool[f"{pref}_count"].fillna(0.0)
        mn = df_pool[f"{pref}_mean"].fillna(0.0)
        sd = df_pool[f"{pref}_stddev"].fillna(0.0)
        df_pool[f"{pref}_sum"] = cnt * mn
        df_pool[f"{pref}_sqrsum"] = cnt * (sd * sd + mn * mn)

    pool_masks = [
        ("core_r3", df_pool["in_core_r3"]),
        ("knee_r3", df_pool["in_knee_r3"]),
        ("supp_maxr", df_pool["in_supp_maxr"]),
        ("all_latest", pd.Series(True, index=df_pool.index)),
    ]
    key_cols = ["cell", "class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"]
    stale_rows, multi_rows, drop_rows = [], [], []

    for pool_name, mask in pool_masks:
        sub = df_pool[mask]
        for key, grp in sub.groupby(key_cols, sort=True):
            c, cls_s, n_amr, lam_v, phy_v = key
            base_k = {
                "pool": pool_name,
                "cell": int(c),
                "class": cls_s,
                "N_AMR": int(n_amr),
                "lambda_tel_Mbps": float(lam_v),
                "phy_rate_Mbps": int(phy_v),
                "n_reps": int(len(grp)),
                "n_generated_total": int(grp["n_generated_valid"].sum()),
            }
            st_row = dict(base_k)
            st_row["n_late_discarded_ttl"] = int(grp["n_late_discarded_ttl"].sum())
            st_row["p_late_ttl_of_generated"] = (
                st_row["n_late_discarded_ttl"] / st_row["n_generated_total"]
                if st_row["n_generated_total"] > 0
                else float("nan")
            )
            for pref in ("stale10", "stale50", "stale500"):
                st_row.update(eam._summarize_group_stats(grp, pref))
            stale_rows.append(st_row)

            mr_row = dict(base_k)
            for col in (
                "p_loss",
                "miss_A_nom",
                "miss_B_nom_T10ms",
                "miss_B_nom_T50ms",
                "miss_B_nom_T500ms",
                "miss_BT_L_eq_T10ms",
                "miss_BT_L_eq_T50ms",
                "miss_BT_L_eq_T500ms",
            ):
                mr_row[col] = float(grp[col].mean())
            mr_row["delta_T50_minus_T10"] = mr_row["miss_B_nom_T50ms"] - mr_row["miss_B_nom_T10ms"]
            mr_row["delta_T500_minus_T10"] = mr_row["miss_B_nom_T500ms"] - mr_row["miss_B_nom_T10ms"]
            mr_row["delta_BT10_minus_B10"] = mr_row["miss_BT_L_eq_T10ms"] - mr_row["miss_B_nom_T10ms"]
            multi_rows.append(mr_row)

            dr_row = dict(base_k)
            tot = st_row["n_generated_total"]
            dq_s = int(grp["n_drop_queue"].sum())
            dr_s = int(grp["n_drop_retry"].sum())
            do_s = int(grp["n_drop_other"].sum())
            lt_s = int(grp["n_late_termination"].sum())
            dr_row.update(
                {
                    "n_drop_queue": dq_s,
                    "n_drop_retry": dr_s,
                    "n_drop_other": do_s,
                    "n_late_termination": lt_s,
                    "p_drop_queue": (dq_s / tot) if tot else float("nan"),
                    "p_drop_retry": (dr_s / tot) if tot else float("nan"),
                    "p_drop_other": (do_s / tot) if tot else float("nan"),
                    "p_late_termination": (lt_s / tot) if tot else float("nan"),
                    "rep_p50_mean_ms": float(grp["lat_p50_ms"].mean()),
                    "rep_p99_mean_ms": float(grp["lat_p99_ms"].mean()),
                    "rep_p99_sd_ms": float(grp["lat_p99_ms"].std(ddof=1)) if len(grp) > 1 else float("nan"),
                    "rep_p99_max_ms": float(grp["lat_p99_ms"].max()),
                    "orders_amr_late_frac_min_mean": float(grp["orders_amr_deliv_late_frac_min"].mean()),
                    "orders_amr_late_frac_max_mean": float(grp["orders_amr_deliv_late_frac_max"].mean()),
                }
            )
            for pref in ("e2e", "wireless", "wired_sw", "wire_ser"):
                dr_row.update(eam._summarize_group_stats(grp, pref))
            drop_rows.append(dr_row)

    pd.DataFrame(stale_rows).to_csv(OUT_DIR / "staleness_summary.csv", index=False)
    pd.DataFrame(multi_rows).to_csv(OUT_DIR / "multirate_summary.csv", index=False)
    pd.DataFrame(drop_rows).to_csv(OUT_DIR / "drop_cause_and_tail_summary.csv", index=False)

    mac_pool_masks = [
        ("core_r3", df_mac["in_core_r3"]),
        ("knee_r3", df_mac["in_knee_r3"]),
        ("supp_maxr", df_mac["in_supp_maxr"]),
        ("all_latest", pd.Series(True, index=df_mac.index)),
    ]
    mac_key_cols = ["cell", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"]
    mac_sum_rows = []
    for pool_name, mask in mac_pool_masks:
        sub = df_mac[mask]
        for key, grp in sub.groupby(mac_key_cols, sort=True):
            c, n_amr, lam_v, phy_v = key
            mac_sum_rows.append(
                {
                    "pool": pool_name,
                    "cell": int(c),
                    "N_AMR": int(n_amr),
                    "lambda_tel_Mbps": float(lam_v),
                    "phy_rate_Mbps": int(phy_v),
                    "n_reps": int(len(grp)),
                    "ap_tx_pkts_mean": float(grp["ap_tx_pkts"].mean()),
                    "ap_tx_retry_ratio_mean": float(grp["ap_tx_retry_ratio"].mean()),
                    "ap_retry_drops_mean": float(grp["ap_retry_limit_drops"].mean()),
                    "ap_frame_seq_mean_ms": float(grp["ap_frame_seq_mean_ms"].mean()),
                    "ap_frame_seq_max_ms": float(grp["ap_frame_seq_max_ms"].max()),
                    "amr_tx_pkts_sum_mean": float(grp["amr_tx_pkts_sum"].mean()),
                    "amr_tx_retry_ratio_mean": float(grp["amr_tx_retry_ratio"].mean()),
                    "amr_retry_drops_sum_mean": float(grp["amr_retry_limit_drops_sum"].mean()),
                    "amr_retry_drops_max": float(grp["amr_retry_limit_drops_max"].max()),
                    "amr_frame_seq_mean_ms": float(grp["amr_frame_seq_mean_ms"].mean()),
                    "ap_sched_granted_mean": float(grp["ap_sched_granted"].mean()),
                    "ap_sched_slot_deferrals_mean": float(grp["ap_sched_slot_deferrals"].mean()),
                    "amr_sched_granted_sum_mean": float(grp["amr_sched_granted_sum"].mean()),
                    "amr_sched_slot_deferrals_sum_mean": float(grp["amr_sched_slot_deferrals_sum"].mean()),
                    "ap_eth_rx_util_pct_mean": float(grp["ap_eth_rx_util_pct"].mean()),
                    "ap_eth_tx_mbps_mean": float(grp["ap_eth_tx_mbps"].mean()),
                    "ap_eth_rx_mbps_mean": float(grp["ap_eth_rx_mbps"].mean()),
                }
            )
    pd.DataFrame(mac_sum_rows).to_csv(OUT_DIR / "mac_phy_summary.csv", index=False)
    export_envelope_screen(df_cls, OUT_DIR)
    print(f"[sync] Synchronized Project Validation/tables/extra in {time.time() - t0:.1f}s")


def export_envelope_screen(df_cls: pd.DataFrame, out_dir: Path, threshold: float = 0.01) -> None:
    """Export Option A stratified distribution-free order-statistic operating-envelope screen."""
    supp = df_cls[df_cls["in_supp_maxr"]].copy()
    key_cols = ["cell", "class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"]
    rows: List[Dict[str, object]] = []

    def _eval_vec(vals: np.ndarray) -> Tuple[float, float, int, str, float]:
        r_n = int(vals.size)
        k_ex = int(np.sum(vals > threshold))
        if k_ex == 0:
            st = "all_le"
            p_ok_lcb = float(0.05 ** (1.0 / r_n))
        elif k_ex == r_n:
            st = "all_gt"
            p_ok_lcb = 0.0
        else:
            st = "mixed"
            p_ok_lcb = float(scipy_stats.beta.ppf(0.05, r_n - k_ex, k_ex + 1))
        return float(np.min(vals)), float(np.max(vals)), k_ex, st, p_ok_lcb

    for key, grp in supp.groupby(key_cols, sort=True):
        c, cls_s, n_amr, lam_v, phy_v = key
        r_n = int(len(grp))
        stratum = "confirmatory" if r_n >= 22 else "exploratory"
        y_b = grp["miss_B_nom_T10ms"].to_numpy(dtype=float)
        eff_col = "miss_A_nom" if str(cls_s) in ("dds", "orders") else "miss_B_nom_T10ms"
        y_e = grp[eff_col].to_numpy(dtype=float)

        min_b, max_b, k_b, st_b, lcb_b = _eval_vec(y_b)
        min_e, max_e, k_e, st_e, lcb_e = _eval_vec(y_e)
        rows.append(
            {
                "cell": int(c),
                "class": str(cls_s),
                "N_AMR": int(n_amr),
                "lambda_tel_Mbps": float(lam_v),
                "phy_rate_Mbps": int(phy_v),
                "stratum": stratum,
                "n_reps": r_n,
                "min_miss_B": min_b,
                "max_miss_B": max_b,
                "k_exceed_B": k_b,
                "state_B": st_b,
                "p_ok_lcb95_B": lcb_b,
                "min_miss_eff": min_e,
                "max_miss_eff": max_e,
                "k_exceed_eff": k_e,
                "state_eff": st_e,
                "p_ok_lcb95_eff": lcb_e,
            }
        )

    out_df = pd.DataFrame(rows).sort_values(key_cols).reset_index(drop=True)
    out_df.to_csv(out_dir / "envelope_screen_option_a.csv", index=False)


if __name__ == "__main__":
    sync_all()

