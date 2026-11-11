import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import schedule_geometry as sg  # noqa: E402


def test_state_and_orders_bounds_at_the_documented_points():
    assert sg.worst_case_wait_ms("state", 80, 12) == pytest.approx(90.0)
    assert sg.worst_case_wait_ms("state", 80, 54) == pytest.approx(48.0)
    # AP's 39 slots merge into one 21.84 ms block: longest gap is 90 - 21.84 ms.
    assert sg.ap_block_ms(80, 12) == pytest.approx(21.84)
    assert sg.worst_case_wait_ms("orders", 80, 12) == pytest.approx(68.16)
    assert sg.worst_case_wait_ms("orders", 80, 54) == pytest.approx(48.0 - 15.6)


def test_wired_only_classes_have_no_schedule_wait():
    for cls in ("dds", "telemetry"):
        assert sg.worst_case_wait_ms(cls, 80, 12) == 0.0


def test_unknown_class_or_geometry_fails_loudly():
    with pytest.raises(ValueError):
        sg.worst_case_wait_ms("video", 10, 54)
    with pytest.raises(ValueError):
        sg.worst_case_wait_ms("state", 15, 54)


def test_geometry_matches_committed_capacity_matrix():
    text = (ROOT / "docs" / "capacity.md").read_text()
    rows = re.findall(r"\| (54|12) Mbps \| (\d+) \| (\d+) \| (\d+) \(([\d.]+)\) \|", text)
    assert len(rows) == 10, "expected the 2 PHY x 5 fleet-size operating-limit matrix"
    for phy, n, t_super, k, block in rows:
        phy, n = int(phy), int(n)
        assert sg.superframe_ms(n, phy) == pytest.approx(float(t_super)), (phy, n)
        assert sg.AP_SLOTS[phy][n] == int(k), (phy, n)
        assert sg.ap_block_ms(n, phy) == pytest.approx(float(block)), (phy, n)


def test_scheduled_utilization_values():
    # State: one packet per AMR per superframe slot at 10 Hz; stable only while T_super <= 100 ms.
    assert sg.scheduled_utilization("state", 80, 12) == pytest.approx(0.9)
    assert sg.scheduled_utilization("state", 80, 54) == pytest.approx(0.48)
    # Orders: 80 AMRs x 5 Hz = 400/s into 39 AP slots per 90 ms superframe = 36/39.
    assert sg.scheduled_utilization("orders", 80, 12) == pytest.approx(36 / 39)
    # At 54 Mbps an exchange (170 us + 28 us DIFS) is about half a 400 us slot, so the merged block holds
    # about 2 frames per slot: 78 frames, not 39.
    assert sg.scheduled_utilization("orders", 80, 54) == pytest.approx(80 * 5 * 0.048 / 78)
    assert sg.scheduled_utilization("dds", 80, 12) == 0.0


def test_ap_capacity_equals_slot_count_at_12mbps_and_about_double_at_54mbps():
    # 12 Mbps: the 550.133 us cycle is slightly under the 560 us slot (K = 39 measured by saturating the AP).
    assert [sg.ap_frames_per_superframe(n, 12) for n in (5, 10, 20, 40, 80)] == [1, 1, 3, 10, 39]
    # 54 Mbps: the 198.133 us cycle fits about twice into a 400 us slot.
    assert [sg.ap_frames_per_superframe(n, 54) for n in (5, 10, 20, 40, 80)] == [2, 2, 4, 16, 78]
