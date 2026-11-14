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
    assert perf["paired_rss_diff_mib_mean"] < 0.0
    assert perf["paired_rss_pct_change_mean"] < 0.0
    assert perf["paired_rss_decreased_count"] == 12
    assert perf["paired_rss_increased_count"] == 0
    assert perf["by_namr_tel"][0]["paired_rss_diff_mib_mean"] < 0.0
    assert perf["campaign_10560_projection"]["n_unique_loads"] == 8

    # Subset / canary mode: remove even cells from opt_dir & opt_manifest (like Cells {1,3,5} CSMA subset)
    for cell in (2, 4, 6):
        for rep in (0, 1):
            rc.RunSpec(cell, rep, 5, 54, "2000us", rep).sca_path(opt_dir).unlink()
    om_sub_path = tmp_path / "opt_sub_manifest.csv"
    pd.DataFrame([r for r in rows_opt if r["cell"] in (1, 3, 5)]).to_csv(om_sub_path, index=False)

    with pytest.raises(RuntimeError, match="Directory file stem mismatch"):
        ve.compare_sca_directories(base_dir, opt_dir, allow_subset=False)
    sub_res = ve.compare_sca_directories(base_dir, opt_dir, allow_subset=True)
    assert sub_res["passed"] is True
    assert sub_res["n_files"] == 6
    assert sub_res["subset_mode"] is True
    sub_perf = ve.compare_manifests(bm_path, om_sub_path, allow_subset=True)
    assert sub_perf["n_paired_runs"] == 6

    # Negative control: 1 modified scalar in subset mode still fails
    bad_opt = rc.RunSpec(1, 0, 5, 54, "2000us", 0).sca_path(opt_dir)
    bad_opt.write_text(
        bad_opt.read_text(encoding="utf-8").replace("packetSentToPeer:count 550", "packetSentToPeer:count 549"),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Raw .sca equivalence failed"):
        ve.compare_sca_directories(base_dir, opt_dir, allow_subset=True)


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

    # Negative check 3: non-Debug section re-enables recording
    bad_sec_ini = tmp_path / "bad_sec.ini"
    base_ini = cp.INI_PATH.read_text(encoding="utf-8")
    bad_sec_ini.write_text(
        base_ini.replace("[Config Cell1_Sweep]\n", "[Config Cell1_Sweep]\n**.statistic-recording = true\n"),
        encoding="utf-8",
    )
    assert cp.check_no_production_recording_overrides(bad_sec_ini) is False

    # Negative check 4: production config extends Debug
    bad_ext_ini = tmp_path / "bad_ext.ini"
    bad_ext_ini.write_text(
        base_ini.replace("extends = Wired_FIFO, Radio_CSMA, Point", "extends = Wired_FIFO, Radio_CSMA, Point, Debug"),
        encoding="utf-8",
    )
    assert cp.check_no_production_recording_overrides(bad_ext_ini) is False

    # Negative check 5: duplicate recording key in [General]
    bad_dup_ini = tmp_path / "bad_dup.ini"
    bad_dup_ini.write_text(
        base_ini.replace("**.scalar-recording = true", "**.scalar-recording = true\n**.statistic-recording = true"),
        encoding="utf-8",
    )
    assert cp.check_no_production_recording_overrides(bad_dup_ini) is False


def test_run_campaign_resolves_and_enforces_jemalloc_and_manifest_consistency(tmp_path, monkeypatch):
    import signal

    path, ver, sha = rc.resolve_jemalloc()
    assert path == rc.DEFAULT_JEMALLOC_PATH
    assert len(sha) == 64
    assert ver != ""

    # Gate succeeds with exact sha, fails on wrong sha
    assert rc.check_jemalloc_gate(path, expected_sha256=sha.upper())[2] == sha
    with pytest.raises(RuntimeError, match="jemalloc SHA-256 mismatch"):
        rc.check_jemalloc_gate(path, expected_sha256="0" * 64)

    # Disabled jemalloc
    assert rc.resolve_jemalloc(None) == ("", "disabled", "")
    with pytest.raises(FileNotFoundError):
        rc.resolve_jemalloc(str(tmp_path / "nonexistent_jemalloc.so"))

    # Pinned launch CLI enforcement
    monkeypatch.setattr(rc, "get_git_state", lambda *a, **k: ("abc123", False))
    monkeypatch.setattr(rc, "check_library_gate", lambda *a, **k: "ab" * 32)
    monkeypatch.setattr(rc, "enumerate_cell_runs", lambda cell, repeat=22: [])
    old = signal.getsignal(signal.SIGTERM)
    try:
        base = ["--expected-lib-sha256", "ab" * 32, "--out-dir", str(tmp_path / "o"), "--evidence-dir", str(tmp_path / "e")]
        with pytest.raises(RuntimeError, match="expected-jemalloc-sha256"):
            rc.main(base)
        with pytest.raises(RuntimeError, match="refuses --no-jemalloc"):
            rc.main(base + ["--no-jemalloc"])
        with pytest.raises(RuntimeError, match="Cannot combine --no-jemalloc"):
            rc.main(base + ["--no-jemalloc", "--expected-jemalloc-sha256", sha])
        # Canary mode explicitly opts out of pinned jemalloc
        rc.main(base + ["--no-jemalloc", "--allow-unpinned-jemalloc"])
    finally:
        signal.signal(signal.SIGTERM, old)

    # manifest_has_matching_run & validate_manifest_consistency
    spec = rc.RunSpec(2, 42, 80, 12, "300us", 0)
    out_dir = tmp_path / "camp"
    manifest = tmp_path / "ev" / "manifest.csv"
    logs = tmp_path / "ev" / "logs"

    def fake_runner(s, odir, log_path, _sim_limit):
        write_valid_sca(s.sca_path(odir), s)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n", encoding="utf-8")
        return 0, 10_000

    res = rc.execute_run_with_retry(
        spec, out_dir=out_dir, manifest_path=manifest, log_dir=logs,
        lib_sha256="lib1", config_sha256="cfg1", jemalloc_sha256="jem1", runner=fake_runner,
    )
    assert res["status"] == "completed"
    assert rc.manifest_has_matching_run(manifest, spec, "lib1", config_sha256="cfg1", jemalloc_sha256="jem1") is True
    assert rc.manifest_has_matching_run(manifest, spec, "lib1", config_sha256="cfg1", jemalloc_sha256="jem2") is False
    assert rc.manifest_has_matching_run(manifest, spec, "lib1", config_sha256="cfg1", jemalloc_sha256="") is False

    # Consistency check rejects differing provenance and mixed rows
    rc.validate_manifest_consistency(manifest, "lib1", "cfg1", "jem1")
    with pytest.raises(RuntimeError, match="does not match current launch"):
        rc.validate_manifest_consistency(manifest, "lib1", "cfg1", "")
    with pytest.raises(RuntimeError, match="does not match current launch"):
        rc.validate_manifest_consistency(manifest, "lib1", "cfg1", "jem2")

    df = pd.read_csv(manifest)
    df_mixed = pd.concat([df, df.assign(jemalloc_sha256="", run_number=43)], ignore_index=True)
    df_mixed.to_csv(manifest, index=False)
    with pytest.raises(RuntimeError, match="Mixed provenance rows"):
        rc.validate_manifest_consistency(manifest, "lib1", "cfg1", "jem1")


