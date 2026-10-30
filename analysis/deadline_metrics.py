"""Deadline-miss metrics and offline quantile evaluators for the Matrix Factory Twin study.

Implements the application-consumption and statistical contract closed in
docs/decisions.md and traffic_class_evidence_matrix.md (Item 7: Choice + Verify):

* Definition A (continuous relative transport deadline, section 1.2) and
  Definition B (discrete NER tick-grid consumption instant, sections 1.3 / 1.3.1:
  c = phi_T + ceil((g - phi_T + L_c) / T) * T, on time iff a <= c, non-strict).
  These rules reflect the Java twin's Time Management Component (MainSimulator.java)
  rather than generic VDA 5050, DDS, OPC UA, or MQTT protocol specifications.
* Working lead time L_c = D_c; the maintainers' freshness variant L_c = T for
  State/Telemetry is obtained by passing ``lead_ms=tick_ms``.
* Replication-global tick-grid phase phi_T ~ U(0, T) drawn on Stream 1 (rng-1)
  (section 1.8): identical across all sinks and paired cells within a replication.
* Accounting filters (section 1.5): discard g < warm-up (5.0 s), discard
  c(g, L_horizon=100 ms, T_0=10 ms, phi_0) > sim-time-limit (60.0 s), and
  partition valid generations into six mutually exclusive bins:
  On_Time / Late_Arrival / Late_Termination / Drop_Queue / Drop_Retry / Drop_Other.
* Discrete staleness in ticks for delivered State/Telemetry packets under
  Zero-Order Hold (section 1.1).
* Offline evaluation of Miss_A / Miss_B from the 25-point conditional delivery
  delay quantile table (Eq. 10), including additive delay-perturbation shifts
  (``shift_ms >= 0``) for sensitivity analysis (e.g., domain-translation overhead
  or Wagner et al.'s proposed 20 Hz teleoperation extension) without re-running
  OMNeT++.
* Replication-level Student-t confidence intervals and pooled Wilson score upper
  bounds for zero-miss boundary regimes (section 1.6).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence

import numpy as np
from scipy import stats

PS_PER_S = 10**12
PS_PER_MS = 10**9

CLASSES = ("orders", "dds", "state", "telemetry")
D_SPECTRUM_MS = (1, 2, 5, 10, 20, 50, 100)                       # decisions.md section 1.7
QUANTILE_LEVELS = (0.000, 0.010, 0.020, 0.050, 0.100, 0.150, 0.200, 0.250,
                   0.300, 0.400, 0.500, 0.600, 0.700, 0.750, 0.800, 0.850,
                   0.900, 0.920, 0.950, 0.970, 0.980, 0.990, 0.995, 0.999,
                   1.000)                                       # section 5.3 (25 fixed levels)
NOMINAL_D_MS = {"orders": 50, "dds": 5, "state": 50, "telemetry": 100}  # Tier 1 markers (Q2)
T_PRIMARY_MS = 10                                                 # T_min (Q1, maintainer-confirmed)
T_OFFLINE_MS = (50, 500)                                          # offline sensitivity
WARMUP_S = 5.0                                                    # omnetpp.ini warmup-period
SIM_LIMIT_S = 60.0                                                # omnetpp.ini sim-time-limit

DROP_BINS = {"queue": "Drop_Queue", "retry": "Drop_Retry", "other": "Drop_Other"}


# --------------------------------------------------------------------------- time helpers
def _ps(ms: float) -> int:
    """Milliseconds -> integer picoseconds."""
    return int(round(float(ms) * PS_PER_MS))


def to_ps(seconds) -> np.ndarray:
    """Seconds (finite floats) -> int64 picoseconds."""
    return np.rint(np.asarray(seconds, dtype=np.float64) * PS_PER_S).astype(np.int64)


def _ceil_div(x, t):
    """Exact integer ceil(x / t) for t > 0 (works on int64 arrays and ints)."""
    return -((-x) // t)


def delay_ms(g, a) -> np.ndarray:
    """End-to-end delay a - g in ms (exact via picoseconds); NaN where undelivered."""
    g = np.asarray(g, dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)
    fin = np.isfinite(a)
    d = (to_ps(np.where(fin, a, 0.0)) - to_ps(g)) / PS_PER_MS
    return np.where(fin, d, np.nan)


# --------------------------------------------------------------------------- Definition A / B
def consumption_instant_ps(g_ps, lead_ps: int, tick_ps: int, phase_ps: int = 0):
    """c = phi + ceil((g + L - phi) / T) * T: first grid point >= g + L."""
    k = _ceil_div(g_ps + lead_ps - phase_ps, tick_ps)
    return phase_ps + k * tick_ps


def miss_a(g, a, d_ms: float) -> np.ndarray:
    """Definition A: miss if lost (a = inf/NaN) or a - g > D."""
    g_ps = to_ps(g)
    a = np.asarray(a, dtype=np.float64)
    fin = np.isfinite(a)
    a_ps = to_ps(np.where(fin, a, 0.0))
    return ~fin | ((a_ps - g_ps) > _ps(d_ms))


def miss_b(g, a, lead_ms: float, tick_ms: float = T_PRIMARY_MS, phase_ms: float = 0.0) -> np.ndarray:
    """Definition B: miss if lost or a > c (a == c is on time)."""
    g_ps = to_ps(g)
    a = np.asarray(a, dtype=np.float64)
    fin = np.isfinite(a)
    a_ps = to_ps(np.where(fin, a, 0.0))
    c = consumption_instant_ps(g_ps, _ps(lead_ms), _ps(tick_ms), _ps(phase_ms))
    return ~fin | (a_ps > c)


def staleness_ticks(g, a, lead_ms: float, tick_ms: float = T_PRIMARY_MS, phase_ms: float = 0.0) -> np.ndarray:
    """max(0, ceil((a - phi)/T) - ceil((g + L - phi)/T)) for delivered packets; -1 if undelivered."""
    g_ps = to_ps(g)
    a = np.asarray(a, dtype=np.float64)
    fin = np.isfinite(a)
    a_ps = to_ps(np.where(fin, a, 0.0))
    t, ph = _ps(tick_ms), _ps(phase_ms)
    stale = np.maximum(0, _ceil_div(a_ps - ph, t) - _ceil_div(g_ps + _ps(lead_ms) - ph, t))
    return np.where(fin, stale, -1)


# --------------------------------------------------------------------------- accounting (section 1.5)
def valid_mask(g, lead_ms: float, tick_ms: float = T_PRIMARY_MS, phase_ms: float = 0.0,
               warmup_s: float = WARMUP_S, sim_limit_s: float = SIM_LIMIT_S) -> np.ndarray:
    """Keep g >= warm-up and c <= sim-time-limit (filter on c, never on arrival time a)."""
    g_ps = to_ps(g)
    c = consumption_instant_ps(g_ps, _ps(lead_ms), _ps(tick_ms), _ps(phase_ms))
    return (g_ps >= int(to_ps(warmup_s))) & (c <= int(to_ps(sim_limit_s)))


def outcome_counts(g, a, cause, d_ms: float, *, definition: str = "B",
                   lead_ms: Optional[float] = None, horizon_lead_ms: Optional[float] = None,
                   tick_ms: float = T_PRIMARY_MS, phase_ms: float = 0.0,
                   warmup_s: float = WARMUP_S, sim_limit_s: float = SIM_LIMIT_S) -> Dict[str, int]:
    """Mutually exclusive, exhaustive bins over the valid packets."""
    if definition not in ("A", "B"):
        raise ValueError("definition must be 'A' or 'B'")
    lead = d_ms if lead_ms is None else lead_ms
    g = np.asarray(g, dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)
    cause = np.asarray(cause, dtype=object)
    fin = np.isfinite(a)

    unknown = {c for c in set(cause.tolist()) if c not in ("",) and c not in DROP_BINS}
    if unknown:
        raise ValueError(f"unmapped drop cause(s): {sorted(unknown)}")
    if np.any(fin & (cause != "")):
        raise ValueError("a packet cannot be both delivered and dropped")

    hz = lead if horizon_lead_ms is None else horizon_lead_ms
    keep = valid_mask(g, hz, tick_ms, phase_ms, warmup_s, sim_limit_s)
    miss = miss_a(g, a, d_ms) if definition == "A" else miss_b(g, a, lead, tick_ms, phase_ms)
    out = {
        "n_valid": int(keep.sum()),
        "On_Time": int((keep & fin & ~miss).sum()),
        "Late_Arrival": int((keep & fin & miss).sum()),
        "Late_Termination": int((keep & ~fin & (cause == "")).sum()),
    }
    for key, name in DROP_BINS.items():
        out[name] = int((keep & ~fin & (cause == key)).sum())
    total = (
        out["On_Time"]
        + out["Late_Arrival"]
        + out["Late_Termination"]
        + sum(out[n] for n in DROP_BINS.values())
    )
    if total != out["n_valid"]:  # conservation law, section 1.5 item 4
        raise AssertionError(f"packet conservation violated: {total} != {out['n_valid']}")
    return out


def miss_rate(g, a, d_ms: float, *, definition: str = "B", lead_ms: Optional[float] = None,
              horizon_lead_ms: Optional[float] = None, tick_ms: float = T_PRIMARY_MS,
              phase_ms: float = 0.0, warmup_s: float = WARMUP_S,
              sim_limit_s: float = SIM_LIMIT_S) -> float:
    """Miss rate over valid packets (lead time L = D unless ``lead_ms`` is given); NaN if none."""
    lead = d_ms if lead_ms is None else lead_ms
    hz = lead if horizon_lead_ms is None else horizon_lead_ms
    g = np.asarray(g, dtype=np.float64)
    keep = valid_mask(g, hz, tick_ms, phase_ms, warmup_s, sim_limit_s)
    if not keep.any():
        return float("nan")
    m = miss_a(g, a, d_ms) if definition == "A" else miss_b(g, a, lead, tick_ms, phase_ms)
    return float(m[keep].mean())


def replication_phase_ms(base_seed: int, rep: int, tick_ms: float = T_PRIMARY_MS) -> float:
    """phi ~ U(0, T), one draw per replication (section 1.8); same phi in every cell for a given rep."""
    rng = np.random.default_rng([int(base_seed), int(rep)])
    return float(rng.integers(0, _ps(tick_ms))) / PS_PER_MS


# --------------------------------------------------------------------------- offline from the quantile table
def _cdf_knots(delays_ms: Sequence[float], levels: Sequence[float]):
    d = np.asarray(delays_ms, dtype=np.float64)
    q = np.asarray(levels, dtype=np.float64)
    if d.shape != q.shape or d.ndim != 1 or d.size == 0:
        raise ValueError("delays and levels must be 1-D arrays of equal, non-zero length")
    if np.any(np.diff(d) < 0) or np.any(np.diff(q) <= 0):
        raise ValueError("quantile table must be non-decreasing in delay and increasing in level")
    # Collapse repeated delays to the largest quantile level for a right-continuous CDF.
    keep = np.append(d[1:] > d[:-1], True)
    return d[keep], q[keep]


def _cdf(y: float, du, qu) -> float:
    return float(np.interp(y, du, qu, left=0.0, right=1.0))


def _integral_cdf(lo: float, hi: float, du, qu) -> float:
    """Exact integral of the piecewise-linear CDF over [lo, hi]."""
    lo = max(lo, du[0])
    if hi <= lo:
        return 0.0
    xs = np.concatenate(([lo], du[(du > lo) & (du < hi)], [hi]))
    ys = np.interp(xs, du, qu, right=1.0)
    return float(np.sum((xs[1:] - xs[:-1]) * (ys[1:] + ys[:-1]) / 2.0))


def miss_a_from_quantiles(d_ms: float, delays_ms, p_loss: float = 0.0,
                          levels: Sequence[float] = QUANTILE_LEVELS,
                          shift_ms: float = 0.0) -> float:
    """P(miss_A) = p_loss + (1 - p_loss) * P(delay + shift_ms > D | delivered)."""
    if shift_ms < 0.0:
        raise ValueError("shift_ms must be non-negative")
    shifted = np.asarray(delays_ms, dtype=np.float64) + float(shift_ms)
    du, qu = _cdf_knots(shifted, levels)
    return p_loss + (1.0 - p_loss) * (1.0 - _cdf(d_ms, du, qu))


def miss_b_from_quantiles(lead_ms: float, tick_ms: float, delays_ms, p_loss: float = 0.0,
                          levels: Sequence[float] = QUANTILE_LEVELS,
                          shift_ms: float = 0.0) -> float:
    """P(miss_B) = p_loss + (1 - p_loss) * (1/T) * integral_0^T P(delay + shift_ms > L + x) dx."""
    if shift_ms < 0.0:
        raise ValueError("shift_ms must be non-negative")
    shifted = np.asarray(delays_ms, dtype=np.float64) + float(shift_ms)
    du, qu = _cdf_knots(shifted, levels)
    mean_cdf = _integral_cdf(lead_ms, lead_ms + tick_ms, du, qu) / tick_ms
    return p_loss + (1.0 - p_loss) * (1.0 - mean_cdf)


def evaluate_retrospective_profile(
    delays_ms: Sequence[float],
    p_loss: float = 0.0,
    *,
    d_ms: float = 50.0,
    lead_ms: Optional[float] = None,
    tick_ms: float = T_PRIMARY_MS,
    shift_ms: float = 0.0,
    levels: Sequence[float] = QUANTILE_LEVELS,
) -> Dict[str, float]:
    """Evaluate alternative consumption contracts (lead_ms, tick_ms, d_ms) or additive
    delay perturbations (shift_ms >= 0, e.g., domain-translation latency or proposed
    teleoperation cadence sensitivity) offline from the 25 exported delay quantiles.
    """
    eff_lead = d_ms if lead_ms is None else float(lead_ms)
    return {
        "d_ms": float(d_ms),
        "lead_ms": eff_lead,
        "tick_ms": float(tick_ms),
        "shift_ms": float(shift_ms),
        "p_loss": float(p_loss),
        "miss_A": miss_a_from_quantiles(d_ms, delays_ms, p_loss=p_loss, levels=levels, shift_ms=shift_ms),
        "miss_B": miss_b_from_quantiles(eff_lead, tick_ms, delays_ms, p_loss=p_loss, levels=levels, shift_ms=shift_ms),
    }


# --------------------------------------------------------------------------- statistics (section 1.6)
def student_t_halfwidth(values: Sequence[float], confidence: float = 0.95) -> float:
    """Half-width of the Student-t CI of the mean over replications (NaN entries ignored)."""
    x = np.asarray(values, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 2:
        return float("nan")
    s = float(x.std(ddof=1))
    return float(stats.t.ppf(0.5 + confidence / 2.0, n - 1) * s / math.sqrt(n))


def wilson_upper(successes: int, trials: int, confidence: float = 0.95) -> float:
    """Upper endpoint of the two-sided Wilson score interval."""
    if trials <= 0 or successes < 0 or successes > trials:
        return float("nan")
    z = float(stats.norm.ppf(0.5 + confidence / 2.0))
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    radius = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))
    return min(1.0, (centre + radius) / denominator)
