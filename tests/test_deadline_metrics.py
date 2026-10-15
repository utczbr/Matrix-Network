"""Tests built from the vectors in docs/checklist_secao3.md C7 and decisions.md section 6."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deadline_metrics as dm  # noqa: E402

MS = 1e-3


def one_tick_of_phases(delay_ms, n=1000, tick_ms=10):
    """Generation times spread uniformly over one tick (10 us grid), constant delay."""
    g = 10.0 + np.arange(n) * (tick_ms / n) * MS
    return g, g + delay_ms * MS


# ---- checklist C7 verification table (T = 10 ms): measured delay, D, L, Miss_B, Miss_A
@pytest.mark.parametrize("delay,d,lead,exp_b,exp_a", [
    (2, 5, 0, 0.20, 0.0),
    (2, 5, 5, 0.00, 0.0),
    (8, 5, 5, 0.30, 1.0),
    (14, 5, 5, 0.90, 1.0),
    (55, 50, 50, 0.50, 1.0),
])
def test_c7_table_packet_level(delay, d, lead, exp_b, exp_a):
    g, a = one_tick_of_phases(delay)
    assert dm.miss_b(g, a, lead).mean() == pytest.approx(exp_b, abs=1e-3)
    assert dm.miss_a(g, a, d).mean() == exp_a


@pytest.mark.parametrize("delay,d,lead,exp_b,exp_a", [
    (2, 5, 0, 0.20, 0.0),
    (2, 5, 5, 0.00, 0.0),
    (8, 5, 5, 0.30, 1.0),
    (14, 5, 5, 0.90, 1.0),
    (55, 50, 50, 0.50, 1.0),
])
def test_c7_table_from_quantiles(delay, d, lead, exp_b, exp_a):
    table = [delay] * len(dm.QUANTILE_LEVELS)
    assert dm.miss_b_from_quantiles(lead, 10, table) == pytest.approx(exp_b, abs=1e-12)
    assert dm.miss_a_from_quantiles(d, table) == exp_a


# ---- Q1 worked example: g = 3 ms, L = D = 5 ms, T = 10 ms -> c = 10 ms, non-strict boundary
@pytest.mark.parametrize("a_ms,miss", [(9, False), (10, False), (11, True)])
def test_q1_worked_example(a_ms, miss):
    assert bool(dm.miss_b([3 * MS], [a_ms * MS], 5, 10)[0]) is miss


def test_lost_packets_always_miss():
    assert dm.miss_a([1.0], [np.nan], 50)[0] and dm.miss_b([1.0], [np.inf], 50)[0]


def test_phase_shifts_the_grid():
    # phi = 2 ms: grid {2, 12, 22, ...}; g + L = 8 -> c = 12 ms
    assert not dm.miss_b([3 * MS], [12 * MS], 5, 10, phase_ms=2)[0]
    assert dm.miss_b([3 * MS], [12.001 * MS], 5, 10, phase_ms=2)[0]


def test_ceiling_is_exact_on_the_boundary():
    # g + L lands exactly on a grid point (0.30000000000000004 s + 50 ms = 350 ms): c = 350 ms,
    # not one tick later, and an arrival at exactly c is on time, one picosecond later is a miss.
    g = 0.1 + 0.2
    assert not dm.miss_b([g], [0.35], 50, 10)[0]
    assert dm.miss_b([g], [0.35 + 1e-11], 50, 10)[0]


def test_staleness_ticks():
    # g = 3, L = 5, T = 10, a = 25: ceil(25/10) - ceil(8/10) = 3 - 1 = 2; on time -> 0; lost -> -1
    s = dm.staleness_ticks([3 * MS, 3 * MS, 3 * MS], [25 * MS, 9 * MS, np.nan], 5, 10)
    assert s.tolist() == [2, 0, -1]


# ---- section 1.5 filters and bins
def test_filters_use_generation_and_consumption_not_arrival():
    g = np.array([4.9, 5.0, 30.0, 59.9, 59.95, 60.0])
    keep = dm.valid_mask(g, lead_ms=50, tick_ms=10, warmup_s=5.0, sim_limit_s=60.0)
    # g < 5 s dropped; c = ceil((g + 0.05)/0.01)*0.01 > 60 s dropped (59.95 + 0.05 = 60.00 -> c = 60.00 kept)
    assert keep.tolist() == [False, True, True, True, True, False]


def test_bins_are_exhaustive_and_exclusive():
    g = np.array([10.000, 11.000, 12.000, 13.000, 14.000, 15.000, 16.000, 1.0])
    a = np.array([10.002, 11.100, np.nan, np.nan, np.nan, np.nan, 16.003, 1.002])
    cause = np.array(["", "", "queue", "retry", "other", "", "", ""], dtype=object)
    oc = dm.outcome_counts(g, a, cause, 50, definition="A")
    assert oc == {"n_valid": 7, "On_Time": 2, "Late_Arrival": 2,
                  "Drop_Queue": 1, "Drop_Retry": 1, "Drop_Other": 1}


def test_unmapped_drop_cause_is_rejected():
    with pytest.raises(ValueError):
        dm.outcome_counts([10.0], [np.nan], np.array(["mystery"], dtype=object), 50)


def test_miss_b_never_exceeds_miss_a_with_l_equals_d():
    rng = np.random.default_rng(1)
    g = np.sort(rng.uniform(6, 50, 20000))
    a = g + rng.exponential(0.01, g.size)
    for d in dm.D_SPECTRUM_MS:
        assert dm.miss_rate(g, a, d, definition="B") <= dm.miss_rate(g, a, d, definition="A") + 1e-12


# ---- offline quantile evaluation agrees with the packet-level one
def test_offline_matches_packet_level_for_uniform_delay():
    rng = np.random.default_rng(7)
    n = 200_000
    g = rng.uniform(6.0, 50.0, n)
    dly = rng.uniform(0.0, 20.0, n)                       # ms
    a = g + dly * MS
    levels = np.array(dm.QUANTILE_LEVELS)
    q = np.quantile(dly, levels)
    for lead, d in [(5, 5), (10, 10), (20, 20)]:
        packet = dm.miss_b(g, a, lead, 10).mean()
        offline = dm.miss_b_from_quantiles(lead, 10, q)
        assert offline == pytest.approx(packet, abs=0.01)
    assert dm.miss_a_from_quantiles(5, q) == pytest.approx(dm.miss_a(g, a, 5).mean(), abs=0.01)


def test_p_loss_is_added_to_offline_miss():
    table = [1.0] * len(dm.QUANTILE_LEVELS)
    assert dm.miss_a_from_quantiles(5, table, p_loss=0.1) == pytest.approx(0.1)
    assert dm.miss_b_from_quantiles(5, 10, table, p_loss=0.1) == pytest.approx(0.1)


def test_crossing_quantile_table_is_rejected():
    bad = list(range(len(dm.QUANTILE_LEVELS)))[::-1]
    with pytest.raises(ValueError):
        dm.miss_a_from_quantiles(5, bad)


def test_student_t_halfwidth():
    # n = 4, s = 1: t(0.975, 3) / 2 = 3.1824 / 2
    assert dm.student_t_halfwidth([1, 2, 3, 2]) == pytest.approx(3.182446 * np.std([1, 2, 3, 2], ddof=1) / 2, rel=1e-5)
    assert np.isnan(dm.student_t_halfwidth([1.0]))
    assert dm.student_t_halfwidth([0.0, 0.0, 0.0]) == 0.0


def test_replication_phase_is_reproducible_and_in_range():
    p = [dm.replication_phase_ms(0, r) for r in range(50)]
    assert p == [dm.replication_phase_ms(0, r) for r in range(50)]
    assert all(0 <= x < 10 for x in p) and len(set(p)) > 40


def test_common_horizon_puts_every_deadline_on_one_packet_set():
    g, a = np.array([59.95]), np.array([59.951])
    assert dm.miss_rate(g, a, 1, definition="A") == 0.0                          # own horizon: c = 59.96 s, kept
    assert np.isnan(dm.miss_rate(g, a, 1, definition="A", horizon_lead_ms=100))   # c(L=100) = 60.05 s > limit
    oc = dm.outcome_counts(g, a, np.array([""], dtype=object), 1, definition="A", horizon_lead_ms=100)
    assert oc["n_valid"] == 0
