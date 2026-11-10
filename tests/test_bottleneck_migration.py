import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import bottleneck_migration as bm  # noqa: E402
import deadline_metrics as dm  # noqa: E402


def test_paired_contrast_identifies_wireless_dominance():
    # Scheduled cells improve miss rate by 0.20; TAS improves it by only 0.05.
    cell_rate = {1: 0.40, 2: 0.20, 3: 0.38, 4: 0.18, 5: 0.35, 6: 0.15}
    rows = []
    for rep in range(3):
        for cell, rate in cell_rate.items():
            row = {
                "cell": cell, "class": "state", "N_AMR": 40,
                "lambda_tel_Mbps": 95.0, "phy_rate_Mbps": 54, "rep": rep,
            }
            row.update({f"miss_B_{deadline}ms": rate for deadline in dm.D_SPECTRUM_MS})
            rows.append(row)
    result = bm.build_contrasts(pd.DataFrame(rows)).iloc[0]
    assert result["wireless_gain"] == pytest.approx(0.20)
    assert result["wired_fifo_to_tas_gain"] == pytest.approx(0.05)
    assert result["dominant_bottleneck"] == "wireless"


def test_uncongested_vs_saturated_tie_and_deadline_override():
    import numpy as np
    import pandas as pd
    import bottleneck_migration as bm
    import deadline_metrics as dm

    rows = []
    for n_amr, base_miss in [(5, 0.0), (80, 1.0)]:
        for cell in range(1, 7):
            for rep in range(3):
                row = {
                    "cell": cell,
                    "class": "state",
                    "N_AMR": n_amr,
                    "lambda_tel_Mbps": 22.4,
                    "phy_rate_Mbps": 54,
                    "rep": rep,
                }
                for d in dm.D_SPECTRUM_MS:
                    # At d=10ms, make Cell 1..6 show a wired bottleneck for N_AMR=5
                    if d == 10 and n_amr == 5:
                        row[f"miss_B_{d}ms"] = 0.40 if cell in (1, 2) else 0.0
                    else:
                        row[f"miss_B_{d}ms"] = base_miss
                rows.append(row)

    df = pd.DataFrame(rows)
    out_nom = bm.build_contrasts(df).set_index("N_AMR")
    assert out_nom.loc[5, "dominant_bottleneck"] == "none_or_uncongested"
    assert out_nom.loc[80, "dominant_bottleneck"] == "mixed_or_uncertain"

    out_10ms = bm.build_contrasts(df, deadline_ms=10).set_index("N_AMR")
    assert out_10ms.loc[5, "dominant_bottleneck"] == "wired"
    assert np.isclose(out_10ms.loc[5, "wired_fifo_to_tas_gain"], 0.40)


# ---------------------------------------------------------------- structural schedule points
def _frame(cls, n_amr, phy, cell_rate, reps=4):
    rows = []
    for rep in range(reps):
        for cell, rate in cell_rate.items():
            row = {"cell": cell, "class": cls, "N_AMR": n_amr,
                   "lambda_tel_Mbps": 95.0, "phy_rate_Mbps": phy, "rep": rep}
            row.update({f"miss_B_{d}ms": rate for d in dm.D_SPECTRUM_MS})
            rows.append(row)
    return pd.DataFrame(rows)


# Scheduled cells (2, 4, 6) carry a 0.45 schedule penalty; TAS helps by 0.05 in both radio regimes.
STRUCTURAL_RATES = {1: 0.10, 2: 0.55, 3: 0.09, 4: 0.54, 5: 0.05, 6: 0.50}


def test_structural_schedule_wait_is_not_read_as_a_wired_bottleneck():
    frame = _frame("state", 80, 12, STRUCTURAL_RATES)
    row = bm.build_contrasts(frame).iloc[0]  # nominal D = 50 ms, T_super = 90 ms
    assert bool(row["structural_tdma_exceeds_deadline"]) is True
    assert row["schedule_wait_bound_ms"] == pytest.approx(90.0)
    assert row["dominant_bottleneck"] == "structural_schedule_wait"
    assert pd.isna(row["wireless_gain"]) and pd.isna(row["wireless_minus_wired"])
    # Wired contrasts difference cells with the same radio, so they are kept and still correct.
    assert row["wired_fifo_to_tas_gain"] == pytest.approx(0.05)
    assert row["wired_fifo_to_priority_gain"] == pytest.approx(0.01)


def test_just_above_the_structural_bound_the_penalty_rule_still_blocks_wired_dominance():
    # At D = 100 ms the geometry bound (90 ms) no longer reaches the deadline, so the point is not
    # tagged structural. Before rev 4 the same numbers classified as "wired", because the negative
    # wireless gain made (wireless - wired) negative. The penalty rule now labels it correctly.
    frame = _frame("state", 80, 12, STRUCTURAL_RATES)
    row = bm.build_contrasts(frame, deadline_ms=100).iloc[0]
    assert bool(row["structural_tdma_exceeds_deadline"]) is False
    assert bool(row["near_structural"]) is True  # 90 ms is within 10% of 100 ms
    assert row["wireless_gain"] < 0
    assert row["dominant_bottleneck"] == "scheduled_radio_penalty"


def test_orders_structural_at_80_amr_12mbps_but_not_at_54mbps():
    at_12 = bm.build_contrasts(_frame("orders", 80, 12, STRUCTURAL_RATES)).iloc[0]
    assert at_12["schedule_wait_bound_ms"] == pytest.approx(68.16)
    assert bool(at_12["structural_tdma_exceeds_deadline"]) is True
    at_54 = bm.build_contrasts(_frame("orders", 80, 54, STRUCTURAL_RATES)).iloc[0]
    assert bool(at_54["structural_tdma_exceeds_deadline"]) is False


def test_near_structural_flag_for_state_at_80_amr_54mbps():
    row = bm.build_contrasts(_frame("state", 80, 54, STRUCTURAL_RATES)).iloc[0]
    assert row["schedule_wait_bound_ms"] == pytest.approx(48.0)
    assert bool(row["structural_tdma_exceeds_deadline"]) is False
    assert bool(row["near_structural"]) is True  # 48 ms is within 10% of the 50 ms deadline


def test_wired_classes_are_never_structural():
    for cls in ("dds", "telemetry"):
        row = bm.build_contrasts(_frame(cls, 80, 12, STRUCTURAL_RATES)).iloc[0]
        assert bool(row["structural_tdma_exceeds_deadline"]) is False
        assert bool(row["near_structural"]) is False


def test_capacity_limited_schedule_is_a_radio_penalty_not_wired_dominance():
    # Orders at N=80, 12 Mbps and D = 100 ms: the zero-load bound (68.16 ms) is below the deadline,
    # so the point is not tagged structural, yet queueing at ~92% AP utilization leaves the
    # scheduled cells 6 points worse. Wired effects are zero here.
    rates = {1: 0.0, 2: 0.06, 3: 0.0, 4: 0.06, 5: 0.0, 6: 0.06}
    row = bm.build_contrasts(_frame("orders", 80, 12, rates), deadline_ms=100).iloc[0]
    assert bool(row["structural_tdma_exceeds_deadline"]) is False
    assert row["schedule_utilization"] == pytest.approx(36 / 39)
    assert row["wireless_gain"] == pytest.approx(-0.06)
    assert row["wired_fifo_to_tas_gain"] == pytest.approx(0.0)
    assert row["dominant_bottleneck"] == "scheduled_radio_penalty"  # was "wired" before rev 4


def test_large_wired_gain_is_not_hidden_behind_a_small_radio_penalty():
    # Wireless effect -0.06 but a saturated FIFO port makes the wired FIFO-to-TAS gain +0.45.
    rates = {1: 0.50, 2: 0.56, 3: 0.25, 4: 0.31, 5: 0.05, 6: 0.11}
    row = bm.build_contrasts(_frame("orders", 80, 12, rates), deadline_ms=100).iloc[0]
    assert row["wireless_gain"] == pytest.approx(-0.06)
    assert row["wired_fifo_to_tas_gain"] == pytest.approx(0.45)
    assert row["dominant_bottleneck"] == "wired"  # wired clearly dominates
    assert bool(row["scheduled_radio_penalty_flag"]) is True  # the radio penalty is still reported


def test_small_wired_gain_does_not_outweigh_a_larger_radio_penalty():
    rates = {1: 0.10, 2: 0.16, 3: 0.09, 4: 0.15, 5: 0.08, 6: 0.14}
    row = bm.build_contrasts(_frame("orders", 80, 12, rates), deadline_ms=100).iloc[0]
    assert row["wireless_gain"] == pytest.approx(-0.06)
    assert row["wired_fifo_to_tas_gain"] == pytest.approx(0.02)
    assert row["dominant_bottleneck"] == "scheduled_radio_penalty"
    assert bool(row["scheduled_radio_penalty_flag"]) is True


def test_penalty_flag_is_false_without_a_significant_negative_wireless_effect():
    rates = {1: 0.40, 2: 0.10, 3: 0.40, 4: 0.10, 5: 0.40, 6: 0.10}  # scheduled radio helps
    row = bm.build_contrasts(_frame("state", 40, 54, rates)).iloc[0]
    assert bool(row["scheduled_radio_penalty_flag"]) is False
    assert bool(row["wired_tas_penalty_flag"]) is False


def test_wired_tas_penalty_for_telemetry_is_not_read_as_wireless_bottleneck():
    # High-load telemetry above TAS's 44.8 Mbps cap loses ~33% more under TAS (Cells 5,6)
    # than under FIFO (Cells 1,2), while wireless gain is zero. Subtracting negative wired
    # gain made (wireless - wired) positive, which previously mislabelled telemetry as "wireless".
    rates = {1: 0.37, 2: 0.37, 3: 0.37, 4: 0.37, 5: 0.70, 6: 0.70}
    row = bm.build_contrasts(_frame("telemetry", 80, 12, rates)).iloc[0]
    assert row["wireless_gain"] == pytest.approx(0.0)
    assert row["wired_fifo_to_tas_gain"] == pytest.approx(-0.33)
    assert bool(row["wired_tas_penalty_flag"]) is True
    assert row["dominant_bottleneck"] == "wired_tas_penalty"


def test_large_wireless_gain_is_not_hidden_behind_a_small_tas_penalty():
    rates = {1: 0.45, 2: 0.05, 3: 0.45, 4: 0.05, 5: 0.50, 6: 0.10}
    row = bm.build_contrasts(_frame("state", 40, 54, rates)).iloc[0]
    assert row["wireless_gain"] == pytest.approx(0.40)
    assert row["wired_fifo_to_tas_gain"] == pytest.approx(-0.05)
    assert bool(row["wired_tas_penalty_flag"]) is True
    assert row["dominant_bottleneck"] == "wireless"
