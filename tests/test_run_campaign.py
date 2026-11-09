import gzip
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import deadline_metrics as dm  # noqa: E402
import export_lookup as ex  # noqa: E402
import run_campaign as rc  # noqa: E402

SINKS = {
    "orders": "MatrixFactoryNetwork.amr[0].app[1].sink",
    "state": "MatrixFactoryNetwork.fms.app[0].sink",
    "telemetry": "MatrixFactoryNetwork.fms.app[1].sink",
    "dds": "MatrixFactoryNetwork.fms.app[2].sink",
}
COORD = "MatrixFactoryNetwork.experimentCoordinator"


def write_valid_sca(path: Path, spec: rc.RunSpec) -> None:
    """Write a complete Stage-2 .sca file with both scalars and domain-delay statistic blocks."""
    lines = [
        "version 3",
        f"run {spec.config_name}-{spec.run_number}",
        f"attr configname {spec.config_name}",
        f"attr nAmr {spec.n_amr}",
        "attr nSta 4",
        f"attr telInterval {spec.tel_interval}",
        f"attr phyRate {spec.phy_rate_mbps}Mbps",
        f"attr repetition {spec.rep}",
        f"scalar {COORD} tick_phase_offset_10ms_sec 0.002",
        f"scalar {COORD} tick_phase_offset_50ms_sec 0.012",
        f"scalar {COORD} tick_phase_offset_500ms_sec 0.120",
    ]
    for cls in dm.CLASSES:
        lines += [
            f"scalar {COORD} n_generated_total_{cls} 10",
            f"scalar {COORD} n_filtered_warmup_{cls} 0",
            f"scalar {COORD} n_filtered_horizon_{cls} 0",
            f"scalar {COORD} n_generated_valid_{cls} 10",
            f"scalar {COORD} n_delivered_valid_{cls} 9",
            f"scalar {COORD} n_drop_queue_{cls} 1",
            f"scalar {COORD} n_drop_retry_{cls} 0",
            f"scalar {COORD} n_drop_other_{cls} 0",
            f"scalar {COORD} n_late_termination_{cls} 0",
        ]
        for i, q in enumerate(dm.QUANTILE_LEVELS):
            lines.append(f"scalar {COORD} ecdf_{cls}_q_{q:.3f} {1.0 + i * 0.1:.3f}")
        sink = SINKS[cls]
        lines += [
            f"scalar {sink} n_received_total 9",
            f"scalar {sink} n_filtered_warmup 0",
            f"scalar {sink} n_filtered_horizon 0",
            f"scalar {sink} n_valid_delivered 9",
            f"scalar {sink} n_domain_breakdown_valid 9",
            f"scalar {sink} tick_phase_offset_10ms_sec 0.002",
            f"scalar {sink} tick_phase_offset_50ms_sec 0.012",
            f"scalar {sink} tick_phase_offset_500ms_sec 0.120",
        ]
        for d in dm.D_SPECTRUM_MS:
            lines.append(f"scalar {sink} n_miss_A_{d}ms 0")
            lines.append(f"scalar {sink} n_miss_B_{d}ms 0")
        for i, q in enumerate(dm.QUANTILE_LEVELS):
            lines.append(f"scalar {sink} ecdf_q_{q:.3f} {1.0 + i * 0.1:.3f}")
        for stat, mean in (
            ("wirelessDomainDelay_ms", 1.5),
            ("wiredSwitchDelay_ms", 0.3),
            ("wireSerializationAndPropDelay_ms", 0.2),
            ("e2eDelay_ms", 2.0),
        ):
            lines += [
                f"statistic {sink} {stat}",
                "field count 9",
                f"field mean {mean}",
                "field stddev 0.1",
            ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def synthetic_full_grid_specs(repeat: int = 22):
    specs = []
    for cell in rc.CELLS:
        run_num = 0
        for n_amr in ex.LOCKED_GRID_NAMRS:
            for phy in ex.LOCKED_GRID_PHYS:
                for tel in ex.LOCKED_GRID_TELS:
                    for rep in range(repeat):
                        specs.append(rc.RunSpec(cell, run_num, n_amr, phy, tel, rep))
                        run_num += 1
    return specs


def test_parse_runs_output_and_slice_major_ordering():
    raw = (
        "Config: Cell1_Sweep\n"
        "Number of runs: 2\n"
        "Run 0: $nAmr=5, $nSta=4, $phyRate=54Mbps, $telInterval=2000us, $repetition=0\n"
        "Run 1: $nAmr=80, $nSta=4, $phyRate=12Mbps, $telInterval=300us, $repetition=0\n"
    )
    parsed = rc.parse_runs_output(1, raw)
    assert len(parsed) == 2
    assert parsed[1] == rc.RunSpec(1, 1, 80, 12, "300us", 0)

    all_specs = synthetic_full_grid_specs(repeat=22)
    assert len(all_specs) == 10_560
    ordered = rc.order_runs_slice_major(all_specs)
    assert len(ordered) == 10_560
    # Priority slice (80, "300us", 12) comes first, and all 6 cells x 22 reps = 132 runs stay contiguous
    first_slice = ordered[:132]
    assert {s.slice_key for s in first_slice} == {(80, "300us", 12)}
    assert [s.cell for s in first_slice[:6]] == [1, 2, 3, 4, 5, 6]
    assert [s.rep for s in first_slice[:6]] == [0] * 6

    # Dry-run corners: 2 N x 2 PHY x 2 loads x 6 cells x 2 reps = 96 runs
    corners = rc.order_runs_slice_major(all_specs, dry_run_corners=True)
    assert len(corners) == 96

    # Sharding never splits a 6-cell slice
    sharded = [rc.order_runs_slice_major(all_specs, shard=(i, 3)) for i in (1, 2, 3)]
    assert sum(len(s) for s in sharded) == 10_560
    slice_sets = [{r.slice_key for r in s} for s in sharded]
    assert slice_sets[0].isdisjoint(slice_sets[1])
    assert slice_sets[1].isdisjoint(slice_sets[2])
    assert slice_sets[0].isdisjoint(slice_sets[2])


def test_library_sha256_and_disk_space_gates(tmp_path):
    dummy_lib = tmp_path / "lib.so"
    dummy_lib.write_bytes(b"matrix-binary")
    actual_sha = rc.sha256_file(dummy_lib)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        rc.check_library_gate(lib_path=dummy_lib, expected_sha256="0" * 64)
    assert rc.check_disk_space(tmp_path, min_free_gb=0.001) > 0.001
    with pytest.raises(RuntimeError, match="Free disk space"):
        rc.check_disk_space(tmp_path, min_free_gb=1e9)


def test_execute_run_cleans_vec_vci_compresses_sca_and_resumes(tmp_path):
    spec = rc.RunSpec(2, 42, 80, 12, "300us", 0)
    out_dir = tmp_path / "campaign"
    manifest = tmp_path / "evidence" / "manifest.csv"
    logs = tmp_path / "evidence" / "logs"
    calls = []

    def fake_runner(s, odir, log_path, _sim_limit):
        calls.append(s.run_number)
        write_valid_sca(s.sca_path(odir), s)
        # Also create dummy .vec and .vci files to verify deletion
        (odir / f"{s.base_stem()}.vec").write_text("dummy vec\n")
        (odir / f"{s.base_stem()}.vci").write_text("dummy vci\n")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("MAX_RSS_KB=123456\n")
        return 0, 123456

    res1 = rc.execute_run_with_retry(
        spec, out_dir=out_dir, manifest_path=manifest, log_dir=logs, lib_sha256="abc123", runner=fake_runner
    )
    assert res1["status"] == "completed"
    assert spec.sca_gz_path(out_dir).exists()
    assert not spec.sca_path(out_dir).exists()
    assert not (out_dir / f"{spec.base_stem()}.vec").exists()
    assert not (out_dir / f"{spec.base_stem()}.vci").exists()

    df_m = pd.read_csv(manifest)
    assert len(df_m) == 1
    assert df_m.iloc[0]["run_number"] == 42
    assert df_m.iloc[0]["sca_bytes"] > 0
    assert len(df_m.iloc[0]["sca_sha256"]) == 64

    # Second call skips without invoking fake_runner
    res2 = rc.execute_run_with_retry(
        spec, out_dir=out_dir, manifest_path=manifest, log_dir=logs, lib_sha256="abc123", runner=fake_runner
    )
    assert res2["status"] == "skipped"
    assert calls == [42]


def test_truncated_sca_is_rejected_retried_with_same_run_number_and_stops_after_two_failures(tmp_path):
    spec = rc.RunSpec(1, 7, 10, 54, "2000us", 0)
    out_dir = tmp_path / "campaign"
    manifest = tmp_path / "evidence" / "manifest.csv"
    logs = tmp_path / "evidence" / "logs"

    # Case 1: Attempt 1 writes a truncated .sca, Attempt 2 writes a valid .sca -> succeeds on retry
    attempts = []

    def flaky_runner(s, odir, log_path, _sim_limit):
        attempts.append(s.run_number)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n")
        if len(attempts) == 1:
            s.sca_path(odir).write_text("version 3\nrun truncated\n")
            return 0, 1000
        write_valid_sca(s.sca_path(odir), s)
        return 0, 1000

    res = rc.execute_run_with_retry(
        spec, out_dir=out_dir, manifest_path=manifest, log_dir=logs, lib_sha256="abc", runner=flaky_runner
    )
    assert res["status"] == "completed" and res["attempts"] == 2
    assert attempts == [7, 7]  # Retried the exact same run_number

    # Case 2: Both attempts fail -> raises RuntimeError and stops campaign
    spec_bad = rc.RunSpec(1, 8, 10, 54, "2000us", 1)
    bad_attempts = []

    def failing_runner(s, odir, log_path, _sim_limit):
        bad_attempts.append(s.run_number)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("<!> Error: cRuntimeError\n")
        return 1, 500

    with pytest.raises(RuntimeError, match="failed twice"):
        rc.execute_run_with_retry(
            spec_bad, out_dir=out_dir, manifest_path=manifest, log_dir=logs, lib_sha256="abc", runner=failing_runner
        )
    assert bad_attempts == [8, 8]
