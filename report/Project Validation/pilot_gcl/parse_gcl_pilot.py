#!/usr/bin/env python3
"""Parse Cell 6 port-specific eth[0] GCL pilot .sca files with strict conservation checks."""
from pathlib import Path
import pandas as pd
import export_lookup as el

BASE = Path(__file__).resolve().parent
REPORT_DIR = BASE.parent
NOMINAL_D_MS = {"dds": 5, "orders": 50, "state": 50, "telemetry": 100}
CAP_MBPS = 67.20


def extract_run_ledgers_and_mac(sca_dir: Path) -> tuple[pd.DataFrame, dict]:
    run_rows = []
    mac_by_load: dict[float, dict[str, int]] = {}
    for p in sorted(sca_dir.glob("*.sca")):
        attrs, sc = el.parse_sca_file(p)
        tel_str = attrs.get("telInterval", "").strip('"')
        lam = el.TEL_INTERVAL_TO_MBPS[tel_str]
        rep = int(attrs["repetition"])
        coord = sorted({m for m, _ in sc if m.endswith(".experimentCoordinator")})
        assert len(coord) == 1, f"Expected 1 coordinator in {p.name}, got {coord}"
        cm = coord[0]
        for cls in ("orders", "dds", "state", "telemetry"):
            run_rows.append({
                "lambda_tel_Mbps": lam,
                "class": cls,
                "rep": rep,
                "n_generated_valid": int(sc[(cm, f"n_generated_valid_{cls}")]),
                "n_drop_queue": int(sc[(cm, f"n_drop_queue_{cls}")]),
                "n_drop_retry": int(sc[(cm, f"n_drop_retry_{cls}")]),
                "n_drop_other": int(sc[(cm, f"n_drop_other_{cls}")]),
                "n_late_termination": int(sc[(cm, f"n_late_termination_{cls}")]),
            })
        d = mac_by_load.setdefault(lam, {
            "ap_grant_releases": 0,
            "amr_grant_releases": 0,
            "ap_granted_in_slot": 0,
            "wlan_retry_pkts": 0,
        })
        for (mod, name), val in sc.items():
            if name == "scheduledDcf_numGrantReleased":
                if ".ap." in mod:
                    d["ap_grant_releases"] += int(val)
                elif ".amr[" in mod:
                    d["amr_grant_releases"] += int(val)
            elif name == "scheduledDcf_numGrantedInSlot" and ".ap." in mod:
                d["ap_granted_in_slot"] += int(val)
            elif name == "packetSentToPeerWithRetry:count":
                d["wlan_retry_pkts"] += int(val)
    return pd.DataFrame(run_rows), mac_by_load


def main() -> None:
    res_dir = BASE / "results"
    sca_files = sorted(res_dir.glob("*.sca"))
    assert len(sca_files) == 12, f"Expected 12 .sca files in {res_dir}, found {len(sca_files)}"

    summary, ecdf = el.build_tables_from_sca(
        res_dir, strict_conservation=True, expected_reps=3, require_full_grid=False
    )
    summary.to_csv(BASE / "Cell6_GCL_Rebal_summary.csv", index=False)
    ecdf.to_csv(BASE / "Cell6_GCL_Rebal_ecdf.csv", index=False)

    run_df, mac_by_load = extract_run_ledgers_and_mac(res_dir)
    for lam, diag in sorted(mac_by_load.items()):
        assert diag["wlan_retry_pkts"] == 0, f"Unexpected wireless retries at {lam} Mbps: {diag}"

    # Verify bit-identical generated packet counts against frozen Cell 6 archive (N=40, 54 Mbps, rep in {0,1,2})
    full_ref = pd.read_csv(REPORT_DIR / "tables" / "extra" / "run_metrics_full.csv")
    c6_r3 = full_ref[
        (full_ref["cell"] == 6)
        & (full_ref["N_AMR"] == 40)
        & (full_ref["phy_rate_Mbps"] == 54)
        & (full_ref["lambda_tel_Mbps"].isin([45.0, 60.0, 74.7, 85.0]))
        & (full_ref["rep"].isin([0, 1, 2]))
    ]
    merged_gen = run_df.merge(
        c6_r3[["lambda_tel_Mbps", "class", "rep", "n_generated_valid"]],
        on=["lambda_tel_Mbps", "class", "rep"],
        suffixes=("_pilot", "_base"),
    )
    assert len(merged_gen) == 48, f"Expected 48 (load x class x rep) rows, got {len(merged_gen)}"
    mismatch = merged_gen[merged_gen["n_generated_valid_pilot"] != merged_gen["n_generated_valid_base"]]
    assert mismatch.empty, f"n_generated_valid mismatch vs Cell 6 baseline:\n{mismatch}"
    print("Verified exact bit-identical n_generated_valid across all 48 (load x class x rep) series.")

    knee_ref = pd.read_csv(REPORT_DIR / "tables" / "knee_r3" / "lookup_summary.csv")
    supp_ref = pd.read_csv(REPORT_DIR / "tables" / "supp_maxr" / "lookup_summary.csv")

    rows = []
    for _, r in summary.iterrows():
        lam = float(r["lambda_tel_Mbps"])
        cls = r["class"]
        d_nom = NOMINAL_D_MS[cls]
        diag = mac_by_load[lam]

        c6_r3_row = knee_ref[
            (knee_ref["cell"] == 6) & (knee_ref["N_AMR"] == 40)
            & (knee_ref["phy_rate_Mbps"] == 54) & (knee_ref["lambda_tel_Mbps"] == lam)
            & (knee_ref["class"] == cls)
        ].iloc[0]
        c6_r22_row = supp_ref[
            (supp_ref["cell"] == 6) & (supp_ref["N_AMR"] == 40)
            & (supp_ref["phy_rate_Mbps"] == 54) & (supp_ref["lambda_tel_Mbps"] == lam)
            & (supp_ref["class"] == cls)
        ].iloc[0]
        c4_r3_row = knee_ref[
            (knee_ref["cell"] == 4) & (knee_ref["N_AMR"] == 40)
            & (knee_ref["phy_rate_Mbps"] == 54) & (knee_ref["lambda_tel_Mbps"] == lam)
            & (knee_ref["class"] == cls)
        ].iloc[0]
        c4_r22_row = supp_ref[
            (supp_ref["cell"] == 4) & (supp_ref["N_AMR"] == 40)
            & (supp_ref["phy_rate_Mbps"] == 54) & (supp_ref["lambda_tel_Mbps"] == lam)
            & (supp_ref["class"] == cls)
        ].iloc[0]

        fluid_lb_pct = max(0.0, (lam - CAP_MBPS) / lam) * 100.0 if cls == "telemetry" else 0.0

        rows.append({
            "lambda_tel_Mbps": lam,
            "class": cls,
            "D_nom_ms": d_nom,
            "n_reps": int(r["n_reps"]),
            "n_total": int(r["n_total"]),
            "n_Drop_Queue": int(r["n_Drop_Queue"]),
            "n_Drop_Retry": int(r["n_Drop_Retry"]),
            "n_Drop_Other": int(r["n_Drop_Other"]),
            "n_Late_Termination": int(r["n_Late_Termination"]),
            "pilot_p_loss_pct": 100.0 * float(r["p_loss"]),
            "pilot_miss_A_nom_pct": 100.0 * float(r[f"miss_A_{d_nom}ms"]),
            "pilot_miss_B_nom_pct": 100.0 * float(r[f"miss_B_{d_nom}ms"]),
            "pilot_p50_ms": float(r["lat_p50"]),
            "pilot_p95_ms": float(r["lat_p95"]),
            "pilot_p99_ms": float(r["lat_p99"]),
            "fluid_lb_pct": fluid_lb_pct,
            "c6_base_r3_p_loss_pct": 100.0 * float(c6_r3_row["p_loss"]),
            "c6_base_r3_miss_B_pct": 100.0 * float(c6_r3_row[f"miss_B_{d_nom}ms"]),
            "c6_base_r3_p99_ms": float(c6_r3_row["lat_p99"]),
            "c6_base_r22_miss_B_pct": 100.0 * float(c6_r22_row[f"miss_B_{d_nom}ms"]),
            "c6_base_r22_p99_ms": float(c6_r22_row["lat_p99"]),
            "c4_base_r3_p_loss_pct": 100.0 * float(c4_r3_row["p_loss"]),
            "c4_base_r3_miss_B_pct": 100.0 * float(c4_r3_row[f"miss_B_{d_nom}ms"]),
            "c4_base_r3_p99_ms": float(c4_r3_row["lat_p99"]),
            "c4_base_r22_miss_B_pct": 100.0 * float(c4_r22_row[f"miss_B_{d_nom}ms"]),
            "c4_base_r22_p99_ms": float(c4_r22_row["lat_p99"]),
            **diag,
        })

    out = pd.DataFrame(rows).sort_values(["class", "lambda_tel_Mbps"]).reset_index(drop=True)
    out.to_csv(BASE / "gcl_pilot_summary.csv", index=False)

    print("\n=== Telemetry Summary ===")
    tel_cols = [
        "lambda_tel_Mbps", "c6_base_r3_miss_B_pct", "c6_base_r22_miss_B_pct",
        "pilot_p_loss_pct", "pilot_miss_B_nom_pct", "fluid_lb_pct",
        "pilot_p50_ms", "pilot_p95_ms", "pilot_p99_ms",
        "c4_base_r3_miss_B_pct", "c4_base_r22_miss_B_pct",
    ]
    print(out[out["class"] == "telemetry"][tel_cols].to_string(index=False))

    print("\n=== Critical Classes Summary ===")
    crit_cols = [
        "class", "lambda_tel_Mbps", "pilot_p_loss_pct", "pilot_miss_A_nom_pct",
        "pilot_miss_B_nom_pct", "pilot_p50_ms", "pilot_p95_ms", "pilot_p99_ms",
        "c6_base_r3_p99_ms", "ap_grant_releases", "wlan_retry_pkts",
    ]
    print(out[out["class"] != "telemetry"][crit_cols].to_string(index=False))


if __name__ == "__main__":
    main()

