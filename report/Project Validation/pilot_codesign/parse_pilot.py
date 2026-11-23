#!/usr/bin/env python3
"""Parse Cell 4 co-design OMNeT++ pilot .sca files with strict conservation checks."""
from pathlib import Path
import pandas as pd
import export_lookup as el

BASE = Path(__file__).resolve().parent
REPORT_DIR = BASE.parent


def extract_mac_diag(sca_dir: Path) -> dict:
    ap_releases = 0
    amr_releases = 0
    retry_pkts = 0
    granted_ap = 0
    for p in sorted(sca_dir.glob("*.sca")):
        _, sc = el.parse_sca_file(p)
        for (mod, name), val in sc.items():
            if name == "scheduledDcf_numGrantReleased":
                if ".ap." in mod:
                    ap_releases += int(val)
                elif ".amr[" in mod:
                    amr_releases += int(val)
            elif name == "scheduledDcf_numGrantedInSlot" and ".ap." in mod:
                granted_ap += int(val)
            elif name == "packetSentToPeerWithRetry:count":
                retry_pkts += int(val)
    return {
        "ap_grant_releases": ap_releases,
        "amr_grant_releases": amr_releases,
        "ap_granted_in_slot": granted_ap,
        "wlan_retry_pkts": retry_pkts,
    }


def main() -> None:
    core_ref = pd.read_csv(REPORT_DIR / "tables" / "core_r3" / "lookup_summary.csv")
    supp_ref = pd.read_csv(REPORT_DIR / "tables" / "supp_maxr" / "lookup_summary.csv")

    rows = []
    for variant, res_dir, n_amr in [
        ("Cell4_N40_K12", BASE / "results_n40", 40),
        ("Cell4_N80_SplitAP", BASE / "results_n80", 80),
    ]:
        summary, ecdf = el.build_tables_from_sca(
            res_dir, strict_conservation=True, expected_reps=3, require_full_grid=False
        )
        summary.to_csv(BASE / f"{variant}_summary.csv", index=False)
        ecdf.to_csv(BASE / f"{variant}_ecdf.csv", index=False)
        diag = extract_mac_diag(res_dir)
        assert diag["wlan_retry_pkts"] == 0, f"Unexpected wireless retries in {variant}: {diag}"

        b_core = core_ref[
            (core_ref["cell"] == 4) & (core_ref["N_AMR"] == n_amr)
            & (core_ref["phy_rate_Mbps"] == 12) & (core_ref["lambda_tel_Mbps"] == 22.4)
        ].set_index("class")
        b_supp = supp_ref[
            (supp_ref["cell"] == 4) & (supp_ref["N_AMR"] == n_amr)
            & (supp_ref["phy_rate_Mbps"] == 12) & (supp_ref["lambda_tel_Mbps"] == 22.4)
        ].set_index("class")

        for _, r in summary.iterrows():
            cls = r["class"]
            ref3 = b_core.loc[cls]
            ref_max = b_supp.loc[cls]
            rows.append({
                "variant": variant,
                "N_AMR": n_amr,
                "class": cls,
                "n_reps": int(r["n_reps"]),
                "n_total": int(r["n_total"]),
                "pilot_p_loss_pct": 100.0 * float(r["p_loss"]),
                "pilot_miss_A_50_pct": 100.0 * float(r["miss_A_50ms"]),
                "pilot_miss_B_50_pct": 100.0 * float(r["miss_B_50ms"]),
                "pilot_miss_B_100_pct": 100.0 * float(r["miss_B_100ms"]),
                "pilot_p50_ms": float(r["lat_p50"]),
                "pilot_p95_ms": float(r["lat_p95"]),
                "pilot_p99_ms": float(r["lat_p99"]),
                "base_r3_miss_B_50_pct": 100.0 * float(ref3["miss_B_50ms"]),
                "base_r3_p99_ms": float(ref3["lat_p99"]),
                "base_maxR_n_reps": int(ref_max["n_reps"]),
                "base_maxR_miss_B_50_pct": 100.0 * float(ref_max["miss_B_50ms"]),
                "base_maxR_p99_ms": float(ref_max["lat_p99"]),
                **diag,
            })

    out = pd.DataFrame(rows)
    out.to_csv(BASE / "codesign_summary.csv", index=False)
    print(out[out["class"].isin(["orders", "state", "dds"])][
        ["variant", "class", "pilot_p_loss_pct", "pilot_miss_A_50_pct", "pilot_miss_B_50_pct",
         "pilot_miss_B_100_pct", "pilot_p50_ms", "pilot_p99_ms", "base_r3_miss_B_50_pct",
         "ap_grant_releases", "wlan_retry_pkts"]
    ].to_string(index=False))


if __name__ == "__main__":
    main()

