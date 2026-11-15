import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import audit_campaign as ac  # noqa: E402
import run_campaign as rc  # noqa: E402


def _write_complete_auditable_sca(path: Path, spec: rc.RunSpec, *, retries: int = 0) -> None:
    lines = [
        "version 3",
        f"run {spec.config_name}-{spec.run_number}",
        f"attr configname {spec.config_name}",
        f"attr repetition {spec.rep}",
        f"attr runnumber {spec.run_number}",
        f"itervar nAmr {spec.n_amr}",
        "itervar nSta 4",
        f"itervar phyRate {spec.phy_rate_mbps}Mbps",
        f"itervar telInterval {spec.tel_interval}",
    ]
    for cls, deliv in (("orders", 10), ("dds", 10), ("state", 10), ("telemetry", 20)):
        lines += [
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_generated_total_{cls} {deliv + 2}",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_generated_valid_{cls} {deliv}",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_filtered_warmup_{cls} 1",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_filtered_horizon_{cls} 1",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_delivered_valid_{cls} {deliv}",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_drop_queue_{cls} 0",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_drop_retry_{cls} 0",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_drop_other_{cls} 0",
            f"scalar MatrixFactoryNetwork.experimentCoordinator n_late_termination_{cls} 0",
        ]
    retry_val = retries if spec.cell in (1, 3, 5) else 0
    lines.append(f"scalar MatrixFactoryNetwork.ap.wlan[0].mac.dcf packetSentToPeerWithRetry:count {retry_val}")
    lines.append("scalar MatrixFactoryNetwork.ap.wlan[0].mac.dcf.recoveryProcedure retryLimitReached:count 0")
    if spec.cell in (2, 4, 6):
        lines.append("scalar MatrixFactoryNetwork.ap.wlan[0].mac.dcf scheduledDcf_numGrantedInSlot 100")

    sinks = [
        ("MatrixFactoryNetwork.fms.app[0].sink", 10, 0.5, 0.2, 0.1),
        ("MatrixFactoryNetwork.fms.app[1].sink", 20, 0.0, 0.05, 0.15),
        ("MatrixFactoryNetwork.fms.app[2].sink", 10, 0.0, 0.02, 0.04),
    ] + [
        (f"MatrixFactoryNetwork.amr[{i}].app[1].sink", 2 if i < 5 else 0, 0.4, 0.1, 0.05)
        for i in range(spec.n_amr)
    ]
    for mod, cnt, wless, wsw, wser in sinks:
        total = f"{wless + wsw + wser:.12g}" if cnt > 0 else "nan"
        wl_s = f"{wless:.12g}" if cnt > 0 else "nan"
        ws_s = f"{wsw:.12g}" if cnt > 0 else "nan"
        we_s = f"{wser:.12g}" if cnt > 0 else "nan"
        lines.append(f"scalar {mod} n_received_total {cnt + 2}")
        lines.append(f"scalar {mod} n_filtered_warmup 1")
        lines.append(f"scalar {mod} n_filtered_horizon 1")
        lines.append(f"scalar {mod} n_valid_delivered {cnt}")
        for metric, mval in (
            ("e2eDelay_ms", total),
            ("wirelessDomainDelay_ms", wl_s),
            ("wiredSwitchDelay_ms", ws_s),
            ("wireSerializationAndPropDelay_ms", we_s),
        ):
            lines.extend([
                f"statistic {mod} {metric}",
                f"field count {cnt}",
                f"field mean {mval}",
            ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_audit_campaign_passes_and_catches_gaps_and_conservation_drift(tmp_path):
    sca_dir = tmp_path / "sca"
    sca_dir.mkdir()
    specs = []
    for namr in (40, 80):
        for phy in (12, 54):
            for tel in ("300us", "2000us"):
                for cell in range(1, 7):
                    for rep in (0, 1):
                        spec = rc.RunSpec(cell=cell, run_number=rep, n_amr=namr, phy_rate_mbps=phy, tel_interval=tel, rep=rep)
                        _write_complete_auditable_sca(
                            spec.sca_path(sca_dir),
                            spec,
                            retries=7 if (cell in (1, 3, 5) and tel == "300us") else 0,
                        )
                        specs.append(spec)

    manifest = tmp_path / "manifest.csv"
    rows = ["cell,nAmr,phy,telInterval,rep,run_number,exit_code,sca_bytes"]
    for s in specs:
        p = s.sca_path(sca_dir)
        rows.append(f"{s.cell},{s.n_amr},{s.phy_rate_mbps},{s.tel_interval},{s.rep},{s.run_number},0,{p.stat().st_size}")
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")

    snap = tmp_path / "snap.sha256"
    out_json = tmp_path / "audit.json"
    ac.main([
        "--sca-dir", str(sca_dir),
        "--manifest", str(manifest),
        "--expected-reps", "2",
        "--stage-namrs", "40,80",
        "--allow-partial-grid",
        "--snapshot-sha256", str(snap),
        "--out-json", str(out_json),
    ])
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["total_runs"] == 96
    assert report["n_slices"] == 8
    assert report["snapshot_digests_written"] == 97
    snap_lines = snap.read_text(encoding="utf-8").splitlines()
    assert len(snap_lines) == 97
    first_hash, first_path = snap_lines[0].split("  ", 1)
    assert first_hash == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert first_path.endswith("manifest.csv")

    # Negative control 1: gap in replications (delete rep=0, keep rep=1 in one cell)
    victim = rc.RunSpec(cell=1, run_number=0, n_amr=40, phy_rate_mbps=12, tel_interval="2000us", rep=0).sca_path(sca_dir)
    victim.unlink()
    with pytest.raises(RuntimeError, match="Manifest has 1 completed runs missing on disk"):
        ac.audit_campaign(sca_dir, manifest_path=manifest, expected_reps=1, stage_namrs=(40, 80), allow_partial_grid=True)
    with pytest.raises(RuntimeError, match="Non-contiguous replications"):
        ac.audit_campaign(sca_dir, expected_reps=1, stage_namrs=(40, 80), allow_partial_grid=True)

    # Restore victim, then corrupt conservation in a sampled corner file
    bad_spec = rc.RunSpec(cell=2, run_number=0, n_amr=80, phy_rate_mbps=12, tel_interval="300us", rep=0)
    _write_complete_auditable_sca(victim, rc.RunSpec(cell=1, run_number=0, n_amr=40, phy_rate_mbps=12, tel_interval="2000us", rep=0))
    bad_path = bad_spec.sca_path(sca_dir)
    bad_path.write_text(
        bad_path.read_text(encoding="utf-8").replace("n_delivered_valid_orders 10", "n_delivered_valid_orders 9", 1),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Phase 6c conservation/domain audit failed"):
        ac.audit_campaign(sca_dir, expected_reps=2, stage_namrs=(40, 80), allow_partial_grid=True)
