import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import deadline_metrics as dm  # noqa: E402
import run_campaign as rc  # noqa: E402
import verify_equivalence as ve  # noqa: E402
from test_run_campaign import COORD, SINKS, write_valid_sca  # noqa: E402


def _write_full_sca_for_equiv(path: Path, spec: rc.RunSpec, *, include_unwhitelisted: bool = False) -> None:
    write_valid_sca(path, spec)
    extra = [
        "scalar MatrixFactoryNetwork.amr[0].app[0].source packets:count 550",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf packetSentToPeer:count 550",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf packetSentToPeerWithRetry:count 12",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf.recoveryProcedure retryLimitReached:count 0",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf scheduledDcf_numSlotDeferrals 3",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf scheduledDcf_numDeferredOnEnqueue 10",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf scheduledDcf_numGrantReleased 3",
        "scalar MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf scheduledDcf_numGrantedInSlot 550",
    ]
    if include_unwhitelisted:
        extra.append("scalar MatrixFactoryNetwork.radioMedium.propagation propagationCount:count 99999")
    for cls in dm.CLASSES:
        sink = SINKS[cls]
        for tick in (10, 50, 500):
            extra += [
                f"statistic {sink} stalenessTicks_{tick}ms",
                "field count 9",
                "field mean 0.0",
                "field stddev 0.0",
                "field min 0.0",
                "field max 0.0",
                "field sum 0.0",
                "field sqrsum 0.0",
            ]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(extra) + "\n")


def test_compare_sca_pair_passes_when_opt_suppresses_only_unwhitelisted_scalars(tmp_path):
    spec = rc.RunSpec(2, 0, 5, 54, "2000us", 0)
    base = tmp_path / "base.sca"
    opt = tmp_path / "opt.sca"
    _write_full_sca_for_equiv(base, spec, include_unwhitelisted=True)
    _write_full_sca_for_equiv(opt, spec, include_unwhitelisted=False)

    res = ve.compare_sca_pair(base, opt)
    assert res["passed"] is True
    assert res["mismatches"] == []
    assert res["required_scalars_checked"] > 100


def test_compare_sca_pair_detects_missing_whitelisted_scalar_or_value_drift(tmp_path):
    spec = rc.RunSpec(2, 0, 5, 54, "2000us", 0)
    base = tmp_path / "base.sca"
    opt = tmp_path / "opt.sca"
    _write_full_sca_for_equiv(base, spec, include_unwhitelisted=True)
    _write_full_sca_for_equiv(opt, spec, include_unwhitelisted=False)

    # Corrupt one whitelisted MAC counter and remove scheduledDcf_numGrantReleased
    lines = [
        line.replace("packetSentToPeerWithRetry:count 12", "packetSentToPeerWithRetry:count 13")
        for line in opt.read_text(encoding="utf-8").splitlines()
        if "scheduledDcf_numGrantReleased" not in line
    ]
    opt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    res = ve.compare_sca_pair(base, opt)
    assert res["passed"] is False
    assert any("MISSING required scalar" in m and "scheduledDcf_numGrantReleased" in m for m in res["mismatches"])
    assert any("MISMATCH scalar" in m and "packetSentToPeerWithRetry:count" in m for m in res["mismatches"])


def test_compare_sca_directories_and_manifests(tmp_path):
    base_dir = tmp_path / "base"
    opt_dir = tmp_path / "opt"
    base_dir.mkdir()
    opt_dir.mkdir()

    rows_base, rows_opt = [], []
    for cell in range(1, 7):
        for rep in (0, 1):
            spec = rc.RunSpec(cell, rep, 5, 54, "2000us", rep)
            _write_full_sca_for_equiv(spec.sca_path(base_dir), spec, include_unwhitelisted=True)
            _write_full_sca_for_equiv(spec.sca_path(opt_dir), spec, include_unwhitelisted=False)
            rows_base.append({
                "cell": cell, "nAmr": 5, "phy": 54, "telInterval": "2000us",
                "rep": rep, "run_number": rep, "exit_code": 0,
                "wall_seconds": 100.0, "max_rss_kb": 200_000, "sca_bytes": 400_000,
            })
            rows_opt.append({
                "cell": cell, "nAmr": 5, "phy": 54, "telInterval": "2000us",
                "rep": rep, "run_number": rep, "exit_code": 0,
                "wall_seconds": 50.0, "max_rss_kb": 90_000, "sca_bytes": 40_000,
            })

    dir_res = ve.compare_sca_directories(base_dir, opt_dir)
    assert dir_res["passed"] is True
    assert dir_res["n_files"] == 12
    assert dir_res["summary_rows"] == 24
    assert dir_res["bottleneck_migration_rows"] == 4

    bm_path = tmp_path / "base_manifest.csv"
    om_path = tmp_path / "opt_manifest.csv"
    pd.DataFrame(rows_base).to_csv(bm_path, index=False)
    pd.DataFrame(rows_opt).to_csv(om_path, index=False)

    perf = ve.compare_manifests(bm_path, om_path)
    assert perf["n_paired_runs"] == 12
    assert perf["overall_speedup_ratio_of_totals"] == 2.0
    assert perf["opt_peak_rss_mib"] < perf["base_peak_rss_mib"]


def test_check_parameters_whitelist_order_and_wired_ifg_consistency(tmp_path):
    import check_parameters as cp

    assert cp.check_parameters() is True

    # Negative check 1: whitelisted key after **.statistic-recording = false fails
    bad_ini = tmp_path / "bad_order.ini"
    bad_ini.write_text(
        "[General]\n"
        "**.statistic-recording = false\n"
        "**.app[*].source.packets.statistic-recording = true\n",
        encoding="utf-8",
    )
    assert cp.check_statistic_whitelist_order(bad_ini) is False

    # Negative check 2: IFG duration mismatch with NED bitrate fails
    ini_kv = cp.parse_ini_sections(cp.INI_PATH)
    bad_kv = dict(ini_kv)
    bad_kv[("General", "**.eth[*].phyLayer.interFrameGapInserter.duration")] = "0.096us"
    assert cp.check_wired_link_ifg_consistency(bad_kv, cp.NED_PATH) is False


def test_run_campaign_resolves_and_records_jemalloc_metadata(tmp_path):
    path, ver, sha = rc.resolve_jemalloc()
    assert path == rc.DEFAULT_JEMALLOC_PATH
    assert len(sha) == 64
    assert ver != ""

    # Disabled jemalloc
    assert rc.resolve_jemalloc(None) == ("", "disabled", "")

    # Missing path raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        rc.resolve_jemalloc(str(tmp_path / "nonexistent_jemalloc.so"))


