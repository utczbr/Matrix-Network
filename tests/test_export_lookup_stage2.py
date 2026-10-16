import sys
from pathlib import Path

import pytest
import numpy as np

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
