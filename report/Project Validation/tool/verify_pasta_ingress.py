#!/usr/bin/env python3
"""Verify the PASTA-violation asymmetry under 100 Mbps ingress serialization.

Reproduces the Section 5.1 store-and-forward discrete-event test at
(N_AMR=80, 54 Mbps PHY, lambda_tel=149.3 Mbps) on switch port eth[0],
comparing:
  1. 100 Mbps store-and-forward ingress serialization (4 station NICs
     multiplexing Telemetry + DDS, plus AP-bridged State arrivals), vs.
  2. Direct switch arrivals without ingress link serialization.
"""
from __future__ import annotations

import heapq
import numpy as np


WIRE_RATE_BPS = 100e6
SIM_LIMIT_S = 60.0
WARMUP_S = 5.0
HORIZON_LEAD_S = 0.100
TICK_S = 0.010
N_SEEDS = 3
N_AMRS = 80
N_STATIONS = 4
QUEUE_CAP = 80

# Wire byte lengths (untagged ingress -> C-tagged switch egress eth[0])
INGRESS_B = {"dds": 266, "state": 1066, "telemetry": 1466}
EGRESS_B = {"dds": 270, "state": 1070, "telemetry": 1470}


def ser_time(n_bytes: int) -> float:
    return (n_bytes * 8.0) / WIRE_RATE_BPS


def generate_stream(rng: np.random.Generator) -> list[tuple[float, str, int]]:
    """Generate (gen_time, class, ingress_nic_id) over [0, SIM_LIMIT_S)."""
    events: list[tuple[float, str, int]] = []

    # 4 stations: DDS U(9.5, 10.5 ms), Telemetry Exp(300 us)
    for st in range(N_STATIONS):
        t = float(rng.uniform(0.0, 0.010))
        while t < SIM_LIMIT_S:
            events.append((t, "dds", st))
            t += float(rng.uniform(0.0095, 0.0105))

        t = float(rng.uniform(0.0, 0.000300))
        while t < SIM_LIMIT_S:
            events.append((t, "telemetry", st))
            t += float(rng.exponential(0.000300))

    # 80 AMRs via AP link (nic_id = N_STATIONS): State U(90, 110 ms)
    for _amr in range(N_AMRS):
        t = float(rng.uniform(0.0, 0.100))
        while t < SIM_LIMIT_S:
            events.append((t, "state", N_STATIONS))
            t += float(rng.uniform(0.090, 0.110))

    events.sort(key=lambda x: x[0])
    return events


def simulate_switch(events: list[tuple[float, str, int]], with_ingress_ser: bool, phi: float) -> dict[str, float]:
    """Run exact DES of ingress store-and-forward + 80-pkt FIFO eth[0] egress."""
    if with_ingress_ser:
        nic_free = [0.0] * (N_STATIONS + 1)
        arrivals: list[tuple[float, float, str]] = []
        for g, cls, nic in events:
            start = max(g, nic_free[nic])
            end = start + ser_time(INGRESS_B[cls])
            nic_free[nic] = end
            if end < SIM_LIMIT_S:
                arrivals.append((end, g, cls))
        arrivals.sort(key=lambda x: x[0])
    else:
        arrivals = [(g, g, cls) for g, cls, _nic in events]

    # Single-server eth[0] egress MAC + 80-packet DropTailQueue
    # Event heap: (time, kind, payload); kind: 0 = egress finish, 1 = switch arrival
    ev_q: list[tuple[float, int, tuple[float, str] | None]] = []
    for arr_t, g, cls in arrivals:
        ev_q.append((arr_t, 1, (g, cls)))
    heapq.heapify(ev_q)

    sw_queue: list[str] = []
    mac_busy = False

    gen_valid = {"dds": 0, "state": 0, "telemetry": 0}
    drop_valid = {"dds": 0, "state": 0, "telemetry": 0}

    def is_valid(g: float) -> bool:
        if g < WARMUP_S:
            return False
        c_hor = phi + np.ceil((g - phi + HORIZON_LEAD_S) / TICK_S) * TICK_S
        return float(c_hor) <= SIM_LIMIT_S

    while ev_q:
        t, kind, payload = heapq.heappop(ev_q)
        if t > SIM_LIMIT_S:
            break
        if kind == 0:
            if sw_queue:
                nxt = sw_queue.pop(0)
                heapq.heappush(ev_q, (t + ser_time(EGRESS_B[nxt]), 0, None))
            else:
                mac_busy = False
        else:
            assert payload is not None
            g, cls = payload
            valid = is_valid(g)
            if valid:
                gen_valid[cls] += 1
            if not mac_busy:
                mac_busy = True
                heapq.heappush(ev_q, (t + ser_time(EGRESS_B[cls]), 0, None))
            elif len(sw_queue) < QUEUE_CAP:
                sw_queue.append(cls)
            else:
                if valid:
                    drop_valid[cls] += 1

    return {cls: 100.0 * drop_valid[cls] / gen_valid[cls] for cls in ("dds", "state", "telemetry")}


def main() -> None:
    for mode_label, use_ing in [
        ("With 100 Mbps ingress serialization", True),
        ("Without ingress serialization (direct)", False),
    ]:
        agg = {"dds": [], "state": [], "telemetry": []}
        for seed in range(N_SEEDS):
            rng = np.random.default_rng(1000 + seed)
            phi = float(rng.uniform(0.0, TICK_S))
            ev = generate_stream(rng)
            res = simulate_switch(ev, with_ingress_ser=use_ing, phi=phi)
            for k in agg:
                agg[k].append(res[k])
        print(
            f"{mode_label}: "
            f"DDS={np.mean(agg['dds']):.2f}%, "
            f"State={np.mean(agg['state']):.2f}%, "
            f"Telemetry={np.mean(agg['telemetry']):.2f}%"
        )


if __name__ == "__main__":
    main()

