import sys
from pathlib import Path

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import deadline_metrics as dm  # noqa: E402
import export_lookup as ex  # noqa: E402


SINKS = {
    "orders": "MatrixFactoryNetwork.amr[0].app[1].sink",
    "state": "MatrixFactoryNetwork.fms.app[0].sink",
    "telemetry": "MatrixFactoryNetwork.fms.app[1].sink",
    "dds": "MatrixFactoryNetwork.fms.app[2].sink",
}


def scalar(module, name, value):
    return f'scalar {module} "{name}" {value}'


def write_sca(path: Path, *, omit=None, generated=10):
    coordinator = "MatrixFactoryNetwork.experimentCoordinator"
    lines = [
        "attr configname Cell1_Sweep",
        "itervar nAmr 5",
        "itervar telInterval 2000us",
        "itervar phyRate 54Mbps",
        "itervar repetition 0",
    ]
    for tick in (10, 50, 500):
        lines.append(scalar(coordinator, f"tick_phase_offset_{tick}ms_sec", 0.001))
    for cls, sink in SINKS.items():
        values = {
            f"n_generated_valid_{cls}": generated,
            f"n_delivered_valid_{cls}": 7,
            f"n_drop_queue_{cls}": 1,
            f"n_drop_retry_{cls}": 1,
            f"n_drop_other_{cls}": 0,
            f"n_late_termination_{cls}": 1,
        }
        for name, value in values.items():
            if name != omit:
                lines.append(scalar(coordinator, name, value))
        for level in dm.QUANTILE_LEVELS:
            lines.append(scalar(coordinator, f"ecdf_{cls}_q_{level:.3f}", level * 10))

        for name, value in {
            "n_received_total": 7,
            "n_filtered_warmup": 0,
            "n_filtered_horizon": 0,
            "n_valid_delivered": 7,
            "n_domain_breakdown_valid": 7,
        }.items():
            lines.append(scalar(sink, name, value))
        for tick in (10, 50, 500):
            lines.append(scalar(sink, f"tick_phase_offset_{tick}ms_sec", 0.001))
        for deadline in dm.D_SPECTRUM_MS:
            lines.append(scalar(sink, f"n_miss_A_{deadline}ms", 2))
            lines.append(scalar(sink, f"n_miss_B_{deadline}ms", 1))
    path.write_text("\n".join(lines) + "\n")


def test_stage2_uses_real_drop_and_termination_accounting(tmp_path):
    write_sca(tmp_path / "run.sca")
    summary, ecdf = ex.build_tables_from_sca(tmp_path, expected_reps=1)
    assert len(summary) == 4
    assert (summary["n_total"] == 10).all()
    assert np.allclose(summary["p_loss"], 0.2)
    assert (summary["n_Late_Termination"] == 1).all()
    assert np.allclose(summary["miss_B_5ms"], 0.4)
    assert (ecdf.groupby(ex.KEY).size() == 25).all()


def test_stage2_missing_scalar_is_fatal(tmp_path):
    write_sca(tmp_path / "run.sca", omit="n_drop_retry_state")
    with pytest.raises(RuntimeError, match="missing scalar.*n_drop_retry_state"):
        ex.build_tables_from_sca(tmp_path, expected_reps=1)


def test_stage2_full_conservation_is_fatal(tmp_path):
    write_sca(tmp_path / "run.sca", generated=11)
    with pytest.raises(RuntimeError, match="Full conservation failed"):
        ex.build_tables_from_sca(tmp_path, expected_reps=1)


# ---------------------------------------------------------------- contiguous-floor repetition gate
def write_run(directory: Path, cell: int, rep: int) -> None:
    path = directory / f"cell{cell}_rep{rep}.sca"
    write_sca(path)
    text = path.read_text()
    text = text.replace("attr configname Cell1_Sweep", f"attr configname Cell{cell}_Sweep")
    text = text.replace("itervar repetition 0", f"itervar repetition {rep}")
    path.write_text(text)


def write_slice(directory: Path, reps_by_cell: dict) -> None:
    for cell, reps in reps_by_cell.items():
        for rep in reps:
            write_run(directory, cell, rep)


def test_floor_accepts_more_repetitions_than_required_when_all_cells_match(tmp_path):
    write_slice(tmp_path, {cell: range(3) for cell in range(1, 7)})
    summary, _ = ex.build_tables_from_sca(tmp_path, expected_reps=2)
    assert (summary["n_reps"] == 3).all()


def test_floor_rejects_a_gap_in_the_repetition_sequence(tmp_path):
    write_slice(tmp_path, {1: [0, 2]})
    with pytest.raises(RuntimeError, match="contiguous from 0"):
        ex.build_tables_from_sca(tmp_path, expected_reps=1)


def test_floor_rejects_fewer_repetitions_than_required(tmp_path):
    write_slice(tmp_path, {1: [0, 1]})
    with pytest.raises(RuntimeError, match="at least, found only 2"):
        ex.build_tables_from_sca(tmp_path, expected_reps=3)


def test_floor_rejects_unequal_counts_across_the_six_cells_of_a_slice(tmp_path):
    write_slice(tmp_path, {1: range(3), 2: range(2)})
    with pytest.raises(RuntimeError, match="unequal repetition counts"):
        ex.build_tables_from_sca(tmp_path, expected_reps=2)


def test_floor_check_can_be_disabled(tmp_path):
    write_slice(tmp_path, {1: [0, 2]})
    summary, _ = ex.build_tables_from_sca(tmp_path, expected_reps=None)
    assert len(summary) == 4


# ---------------------------------------------------------------- gzip-compressed scalar files
def gzip_in_place(path: Path) -> Path:
    import gzip
    target = path.with_name(path.name + ".gz")
    target.write_bytes(gzip.compress(path.read_bytes()))
    path.unlink()
    return target


def test_gzipped_sca_gives_identical_tables(tmp_path):
    plain_dir, gz_dir = tmp_path / "plain", tmp_path / "gz"
    plain_dir.mkdir(); gz_dir.mkdir()
    write_sca(plain_dir / "run.sca")
    write_sca(gz_dir / "run.sca")
    gzip_in_place(gz_dir / "run.sca")
    s_plain, e_plain = ex.build_tables_from_sca(plain_dir, expected_reps=1)
    s_gz, e_gz = ex.build_tables_from_sca(gz_dir, expected_reps=1)
    assert s_plain.equals(s_gz) and e_plain.equals(e_gz)


def test_plain_and_gzipped_copy_of_the_same_run_is_a_duplicate(tmp_path):
    write_sca(tmp_path / "run.sca")
    write_sca(tmp_path / "copy.sca")
    gzip_in_place(tmp_path / "copy.sca")
    with pytest.raises(RuntimeError, match="duplicate replication rows"):
        ex.build_tables_from_sca(tmp_path, expected_reps=1)


# ---------------------------------------------------------------- domain-delay statistic blocks
DOMAIN_MEANS = {"wireless": 2.0, "wired_switch": 0.5, "wire_serialization": 0.1}
WIRED_ONLY = ("dds", "telemetry")


def add_domain_stats(path: Path, *, drop=None, counts=7, e2e_offset=0.0, wireless_by_class=None) -> None:
    """Append statistic blocks like DeadlineSink's recordAs() writes (count, mean, ..., bins, attr)."""
    lines = []
    for cls, sink in SINKS.items():
        wireless = 0.0 if cls in WIRED_ONLY else DOMAIN_MEANS["wireless"]
        if wireless_by_class and cls in wireless_by_class:
            wireless = wireless_by_class[cls]
        means = {"wirelessDomainDelay_ms": wireless,
                 "wiredSwitchDelay_ms": DOMAIN_MEANS["wired_switch"],
                 "wireSerializationAndPropDelay_ms": DOMAIN_MEANS["wire_serialization"]}
        means["e2eDelay_ms"] = sum(means.values()) + e2e_offset
        for stat, mean in means.items():
            if stat == drop:
                continue
            lines += [f"statistic {sink} {stat}", "attr unit ms", f"field count {counts}",
                      f"field mean {mean}", "field stddev 0.1", "field min 0", "field max 9",
                      "bin\t-inf\t0", "bin\t0\t5\t3", "bin\t5\tinf\t4"]
    with open(path, "a") as f:
        f.write("\n".join(lines) + "\n")


def test_parse_sca_statistics_reads_count_and_mean_and_ignores_bins(tmp_path):
    path = tmp_path / "run.sca"
    write_sca(path)
    add_domain_stats(path)
    stats = ex.parse_sca_statistics(path)
    block = stats[(SINKS["orders"], "wirelessDomainDelay_ms")]
    assert block["count"] == 7 and block["mean"] == pytest.approx(2.0) and block["stddev"] == pytest.approx(0.1)
    assert all(set(v) <= {"count", "mean", "stddev"} for v in stats.values())
    assert len(stats) == 4 * 4  # four classes x (three domains + end-to-end)
    gz = gzip_in_place(path)
    assert ex.parse_sca_statistics(gz) == stats


def test_weighted_mean_weights_by_count_and_skips_empty_sinks():
    assert ex.weighted_mean([(10, 2.0), (30, 4.0)]) == pytest.approx(3.5)
    assert ex.weighted_mean([(0, float("nan")), (5, 1.5)]) == pytest.approx(1.5)
    assert np.isnan(ex.weighted_mean([(0, float("nan"))]))


def test_domain_delay_table_has_one_row_per_class_and_domain(tmp_path):
    write_sca(tmp_path / "run.sca")
    add_domain_stats(tmp_path / "run.sca")
    table = ex.build_domain_delay_table(tmp_path)
    assert len(table) == 12
    orders = table[(table["class"] == "orders")].set_index("domain")
    assert orders.loc["wireless", "mean_ms"] == pytest.approx(2.0)
    assert orders.loc["wired_switch", "mean_ms"] == pytest.approx(0.5)
    assert (orders["n_samples"] == 7).all()
    assert orders["e2e_mean_ms"].tolist() == pytest.approx([2.6, 2.6, 2.6])
    assert (table[table["class"] == "dds"].set_index("domain").loc["wireless", "mean_ms"]) == 0.0


def test_domain_delay_table_fails_on_a_missing_statistic(tmp_path):
    write_sca(tmp_path / "run.sca")
    add_domain_stats(tmp_path / "run.sca", drop="wiredSwitchDelay_ms")
    with pytest.raises(RuntimeError, match="missing statistic wiredSwitchDelay_ms"):
        ex.build_domain_delay_table(tmp_path)


def test_domain_delay_table_fails_when_counts_disagree_with_the_scalar_ledger(tmp_path):
    write_sca(tmp_path / "run.sca")
    add_domain_stats(tmp_path / "run.sca", counts=6)  # scalars say n_domain_breakdown_valid = 7
    with pytest.raises(RuntimeError, match="n_domain_breakdown_valid"):
        ex.build_domain_delay_table(tmp_path)


def test_domain_delay_table_fails_when_components_do_not_sum_to_end_to_end(tmp_path):
    write_sca(tmp_path / "run.sca")
    add_domain_stats(tmp_path / "run.sca", e2e_offset=0.25)
    with pytest.raises(RuntimeError, match="end-to-end mean"):
        ex.build_domain_delay_table(tmp_path)


def test_cli_writes_the_domain_delay_csv_only_when_asked(tmp_path):
    sca_dir, out = tmp_path / "sca", tmp_path / "out"
    sca_dir.mkdir()
    write_sca(sca_dir / "run.sca")
    add_domain_stats(sca_dir / "run.sca")
    base = ["--sca-dir", str(sca_dir), "--out-dir", str(out), "--expected-reps", "1", "--allow-partial-grid"]
    ex.main(base)
    assert not (out / "lookup_domain_delay.csv").exists()
    ex.main(base + ["--domain-delay"])
    written = pd.read_csv(out / "lookup_domain_delay.csv")
    assert len(written) == 12 and set(written["domain"]) == set(DOMAIN_MEANS)
