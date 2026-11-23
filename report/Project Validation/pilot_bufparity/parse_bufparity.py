#!/usr/bin/env python3
"""Parse Cell 3 buffer-parity ablation (TC0=80 pkts) .sca files with strict conservation."""
from pathlib import Path
import pandas as pd
import export_lookup as el

BASE = Path(__file__).resolve().parent
REPORT_DIR = BASE.parent
NOMINAL_D_MS = {"dds": 5, "orders": 50, "state": 50, "telemetry": 100}
LOADS = [85.0, 95.0, 149.3]


def extract_run_ledgers(sca_dir: Path) -> pd.DataFrame:
    rows = []
    for p in sorted(sca_dir.glob("*.sca")):
        attrs, sc = el.parse_sca_file(p)
        lam = el.TEL_INTERVAL_TO_MBPS[attrs.get("telInterval", "").strip('"')]
        rep = int(attrs["repetition"])
        coord = sorted({m for m, _ in sc if m.endswith(".experimentCoordinator")})
        assert len(coord) == 1, f"Expected 1 coordinator in {p.name}, got {coord}"
        cm = coord[0]
        retry_pkts = sum(int(val) for (_, name), val in sc.items() if name == "packetSentToPeerWithRetry:count")
        for cls in ("orders", "dds", "state", "telemetry"):
            rows.append({
                "lambda_tel_Mbps": lam,
                "class": cls,
                "rep": rep,
                "n_generated_valid": int(sc[(cm, f"n_generated_valid_{cls}")]),
                "wlan_retry_pkts": retry_pkts,
            })
    return pd.DataFrame(rows)


def main() -> None:
    res_dir = BASE / "results"
    sca_files = sorted(res_dir.glob("*.sca"))
    assert len(sca_files) == 9, f"Expected 9 .sca files in {res_dir}, found {len(sca_files)}"

    summary, ecdf = el.build_tables_from_sca(
        res_dir, strict_conservation=True, expected_reps=3, require_full_grid=False
    )
    summary.to_csv(BASE / "Cell3_BufParity_summary.csv", index=False)
    ecdf.to_csv(BASE / "Cell3_BufParity_ecdf.csv", index=False)

    run_df = extract_run_ledgers(res_dir)
    full_ref = pd.read_csv(REPORT_DIR / "tables" / "extra" / "run_metrics_full.csv")
    c3_r3_ref = full_ref[
        (full_ref["cell"] == 3)
        & (full_ref["N_AMR"] == 40)
        & (full_ref["phy_rate_Mbps"] == 54)
        & (full_ref["lambda_tel_Mbps"].isin(LOADS))
        & (full_ref["rep"].isin([0, 1, 2]))
    ]
    merged = run_df.merge(
        c3_r3_ref[["lambda_tel_Mbps", "class", "rep", "n_generated_valid"]],
        on=["lambda_tel_Mbps", "class", "rep"],
        suffixes=("_pilot", "_base"),
    )
    assert len(merged) == 36, f"Expected 36 (load x class x rep) rows, got {len(merged)}"
    mismatch = merged[merged["n_generated_valid_pilot"] != merged["n_generated_valid_base"]]
    assert mismatch.empty, f"n_generated_valid mismatch vs Cell 3 baseline:\n{mismatch}"
    print("Verified exact bit-identical n_generated_valid across all 36 (load x class x rep) series.")

    knee_ref = pd.read_csv(REPORT_DIR / "tables" / "knee_r3" / "lookup_summary.csv")
    supp_ref = pd.read_csv(REPORT_DIR / "tables" / "supp_maxr" / "lookup_summary.csv")

    rows = []
    for _, r in summary.iterrows():
        lam = float(r["lambda_tel_Mbps"])
        cls = r["class"]
        d_nom = NOMINAL_D_MS[cls]

        def _pick(df: pd.DataFrame, cell_id: int):
            hit = df[
                (df["cell"] == cell_id) & (df["N_AMR"] == 40)
                & (df["phy_rate_Mbps"] == 54) & (df["lambda_tel_Mbps"] == lam)
                & (df["class"] == cls)
            ]
            return hit.iloc[0]

        c3_3 = _pick(knee_ref, 3)
        c3_22 = _pick(supp_ref, 3)
        c1_3 = _pick(knee_ref, 1)
        c1_22 = _pick(supp_ref, 1)

        rows.append({
            "lambda_tel_Mbps": lam,
            "class": cls,
            "D_nom_ms": d_nom,
            "n_reps": int(r["n_reps"]),
            "n_total": int(r["n_total"]),
            "n_Drop_Queue": int(r["n_Drop_Queue"]),
            "pilot_p_loss_pct": 100.0 * float(r["p_loss"]),
            "pilot_miss_A_nom_pct": 100.0 * float(r[f"miss_A_{d_nom}ms"]),
            "pilot_miss_B_nom_pct": 100.0 * float(r[f"miss_B_{d_nom}ms"]),
            "pilot_p50_ms": float(r["lat_p50"]),
            "pilot_p95_ms": float(r["lat_p95"]),
            "pilot_p99_ms": float(r["lat_p99"]),
            "c3_20pkt_r3_miss_B_pct": 100.0 * float(c3_3[f"miss_B_{d_nom}ms"]),
            "c3_20pkt_r3_p99_ms": float(c3_3["lat_p99"]),
            "c3_20pkt_r22_miss_B_pct": 100.0 * float(c3_22[f"miss_B_{d_nom}ms"]),
            "c3_20pkt_r22_p99_ms": float(c3_22["lat_p99"]),
            "c1_fifo_r3_miss_B_pct": 100.0 * float(c1_3[f"miss_B_{d_nom}ms"]),
            "c1_fifo_r3_miss_A_pct": 100.0 * float(c1_3[f"miss_A_{d_nom}ms"]),
            "c1_fifo_r3_p_loss_pct": 100.0 * float(c1_3["p_loss"]),
            "c1_fifo_r22_miss_B_pct": 100.0 * float(c1_22[f"miss_B_{d_nom}ms"]),
            "c1_fifo_r22_miss_A_pct": 100.0 * float(c1_22[f"miss_A_{d_nom}ms"]),
            "c1_fifo_r22_p_loss_pct": 100.0 * float(c1_22["p_loss"]),
            "c1_fifo_r22_p99_ms": float(c1_22["lat_p99"]),
        })

    out = pd.DataFrame(rows).sort_values(["class", "lambda_tel_Mbps"]).reset_index(drop=True)
    out.to_csv(BASE / "bufparity_summary.csv", index=False)

    print("\n=== Telemetry & Critical Comparison (Cell 1 FIFO 80p vs Cell 3 20p TC0 vs Cell 3 Control 80p TC0) ===")
    print(out[[
        "lambda_tel_Mbps", "class",
        "c1_fifo_r3_p_loss_pct", "c1_fifo_r3_miss_B_pct",
        "c3_20pkt_r3_miss_B_pct", "c3_20pkt_r22_miss_B_pct",
        "pilot_p_loss_pct", "pilot_miss_A_nom_pct", "pilot_miss_B_nom_pct",
        "c3_20pkt_r3_p99_ms", "pilot_p99_ms",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

