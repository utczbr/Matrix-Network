#!/usr/bin/env python3
"""Locked ScheduledDcf schedule geometry and worst-case wireless access waits.

Values mirror ``simulations/omnetpp.ini`` (superframeDuration, numAssignedSlots,
AP slotDuration) and ``docs/SPEC-scheduled-dcf.md`` section 2. They are
cross-checked against the committed ``docs/capacity.md`` matrix by
``tests/test_schedule_geometry.py``; change all of them together.

The bound answers one question: how long can a packet of a class wait for the
scheduled radio before it can even be transmitted, regardless of load? When
that wait reaches the evaluation deadline, misses are a property of the
schedule geometry (structural), not of congestion.

* ``state`` (AMR uplink): one slot per superframe, so the wait is bounded by
  the superframe ``T_super`` (matches the ``capacity.md`` operating-limit matrix).
* ``orders`` (AP downlink): the AP's ``K`` slots merge into one contiguous
  block per superframe, so the longest zero-load wait is the gap between blocks,
  ``T_super - K * s_AP``. This is a LOWER bound on the real wait: Orders are
  Poisson into one shared AP queue, so at high utilization (36 of 39 slots per
  superframe at N=80, 12 Mbps) carryover between superframes adds queueing.
  The 10 s acceptance run measured 49.8% Orders misses at 50 ms, against about
  20% from the zero-load gap alone. Use ``scheduled_utilization`` to see how
  far a point is from the zero-load regime.
* ``dds`` and ``telemetry`` are wired-only: no radio schedule, bound 0.
"""
from __future__ import annotations

import math

from capacity import ORDER_HZ, STATE_HZ  # traffic rates: single source of truth

SUPERFRAME_MS = {
    54: {5: 3.0, 10: 5.0, 20: 9.0, 40: 20.0, 80: 48.0},
    12: {5: 6.0, 10: 10.0, 20: 20.0, 40: 42.0, 80: 90.0},
}
AP_SLOT_MS = {54: 0.40, 12: 0.56}
AP_SLOTS = {
    54: {5: 1, 10: 1, 20: 2, 40: 8, 80: 39},
    12: {5: 1, 10: 1, 20: 3, 40: 10, 80: 39},
}
WIRED_ONLY_CLASSES = ("dds", "telemetry")

# Orders exchange (DATA + SIFS + ACK) durations from calibrate_80211.py, and the requirement ScheduledDcf
# uses (exchange + DIFS, rounded up). Frames inside the AP's merged block go back to back, one DIFS apart,
# so a block holds more than one frame per slot whenever the exchange is shorter than the slot.
DIFS_MS = 0.028
AP_EXCHANGE_MS = {54: 0.17013, 12: 0.52213}
AP_REQUIRED_MS = {54: 0.200, 12: 0.550}


def _lookup(table: dict, n_amr: int, phy_mbps) -> float:
    phy = int(round(float(phy_mbps)))
    n = int(n_amr)
    try:
        return table[phy][n]
    except KeyError as exc:
        raise ValueError(f"no locked schedule geometry for N={n}, PHY={phy} Mbps") from exc


def superframe_ms(n_amr: int, phy_mbps) -> float:
    """Superframe duration T_super in ms."""
    return float(_lookup(SUPERFRAME_MS, n_amr, phy_mbps))


def ap_block_ms(n_amr: int, phy_mbps) -> float:
    """Length of the AP's merged contiguous downlink block in ms."""
    phy = int(round(float(phy_mbps)))
    return float(_lookup(AP_SLOTS, n_amr, phy) * AP_SLOT_MS[phy])


def ap_frames_per_superframe(n_amr: int, phy_mbps) -> int:
    """Orders exchanges the AP can complete per superframe: back-to-back frames (exchange + DIFS apart) may
    start while at least the required exchange time remains in the merged block. At 12 Mbps this equals the
    slot count K (39 at N=80, confirmed by saturating the AP); at 54 Mbps it is about 2K. The single-slot
    54 Mbps case (two frames) has only a 2 us margin."""
    phy = int(round(float(phy_mbps)))
    block = ap_block_ms(n_amr, phy)
    cycle = AP_EXCHANGE_MS[phy] + DIFS_MS
    return int(math.floor((block - AP_REQUIRED_MS[phy]) / cycle + 1e-9)) + 1


def scheduled_utilization(cls: str, n_amr: int, phy_mbps) -> float:
    """Offered load divided by scheduled radio capacity per superframe (0 for wired-only classes).

    state:  one slot per AMR per superframe, so ``STATE_HZ * T_super``.
    orders: ``N * ORDER_HZ * T_super / F`` where F is ``ap_frames_per_superframe`` (all AMRs share one
            merged AP block; F equals K at 12 Mbps and is about 2K at 54 Mbps).
    Values near 1 mean queueing carryover, so the zero-load wait bound understates delay.
    """
    if cls in WIRED_ONLY_CLASSES:
        return 0.0
    t_super_s = superframe_ms(n_amr, phy_mbps) / 1000.0
    if cls == "state":
        return float(STATE_HZ * t_super_s)
    if cls == "orders":
        return float(int(n_amr) * ORDER_HZ * t_super_s / ap_frames_per_superframe(n_amr, phy_mbps))
    raise ValueError(f"unknown traffic class {cls!r}")


def worst_case_wait_ms(cls: str, n_amr: int, phy_mbps) -> float:
    """Worst-case wait for the scheduled radio, in ms (0 for wired-only classes)."""
    if cls in WIRED_ONLY_CLASSES:
        return 0.0
    if cls == "state":
        return superframe_ms(n_amr, phy_mbps)
    if cls == "orders":
        return superframe_ms(n_amr, phy_mbps) - ap_block_ms(n_amr, phy_mbps)
    raise ValueError(f"unknown traffic class {cls!r}")
