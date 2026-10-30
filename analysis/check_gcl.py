"""Check the 802.1Qbv gate schedule in simulations/omnetpp.ini against the wire arithmetic.

Reads ``[Config Wired_TAS]`` (gate durations/offsets) and the application packet
lengths from the INI, then verifies the facts documented as "Verified (analytic)"
in docs/parameters.md section 8, docs/decisions.md section 6, and
traffic_class_evidence_matrix.md:

* the four windows are disjoint, inside the cycle and the durations add up to the cycle;
* the windows match the intended schedule (Orders [0,100), DDS [100,300), State
  [300,500), Telemetry [500,1000) us), using the convention of the INI comment:
  durations=[w, cycle-w], initiallyOpen=true, offset = cycle - start (mod cycle);
* frames per window under INET 4.7.0 PeriodicGate's implicit guard band, evaluated
  for two accounting conventions: L2 frame bits (UDP+IP+[C-tag]+MAC+FCS = +46/+50 B)
  and full physical wire occupancy (+8 B preamble/SFD + 12 B IFG = +66/+70 B).
  Orders/State/Telemetry give the same integer count (1/2/4) under both; DDS does NOT
  (9 on the wire, 10 under L2 only: 250 B = 20.0 us -> 200/20 = 10).  The repository
  documents the wire convention (9); which convention INET really applies is the
  open in-simulation item of checklist C8 and is reported, not assumed, here;
* full IP MTU (1500 B IP packet = 1518/1522 B L2 frame = 1538/1542 B wire occupancy,
  requiring 121.44..123.36 us at 100 Mbps) vs. the 100 us TC3 window (and why even
  a 120 us window is insufficient for full-MTU frames);
* corrected VDA 5050 path-graph scaling (Wagner et al., 2026: simple path E = N - 1),
  Fast-RTPS framing benchmark (Profanter et al., 2019: +88 B UDP payload overhead),
  and telemetry payload ceiling (4 x 1400 B per 1 ms = 44.8 Mbps);
* window occupancy for the offered load of the sweep (informational).

It does NOT replace the in-simulation check of checklist C8 (record gateState:vector
in Cell 5 and compare with the windows printed here).

Usage: python check_gcl.py [path/to/omnetpp.ini]      (exit code 1 if a check fails)
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

LINK_MBPS = 100.0                   # wired rate (Q5); bits per us == Mbps
L2_OVERHEAD_UNTAGGED_B = 46         # UDP 8 + IP 20 + Ethernet MAC 14 + FCS 4 (checked by PeriodicGate)
PHY_PREAMBLE_IFG_B = 20             # 8 B PHY preamble/SFD + 12 B inter-frame gap (wire occupancy)
OVERHEAD_UNTAGGED_B = L2_OVERHEAD_UNTAGGED_B + PHY_PREAMBLE_IFG_B  # 66 B total wire overhead untagged
TAG_B = 4                           # 802.1Q C-tag
TOL = 1e-9

# Standard MTU and published benchmark constants (traffic_class_evidence_matrix.md)
IP_MTU_B = 1500                     # Conventional Ethernet IPv4 MTU (1472 B UDP payload)
UDP_IPV4_HEADER_B = 28              # 20 B IPv4 + 8 B UDP
FULL_MTU_UDP_PAYLOAD_B = IP_MTU_B - UDP_IPV4_HEADER_B  # 1472 B
WAGNER_ORDER_BASE_B = 206           # Wagner et al. (2026) Table I: 206 + 154*N_nodes + 434*N_edges
WAGNER_ORDER_NODE_B = 154
WAGNER_ORDER_EDGE_B = 434
WAGNER_STATE_BASE_B = 522           # Wagner et al. (2026) Table I: 522 + 75*N_nodes + 91*N_edges
WAGNER_STATE_NODE_B = 75
WAGNER_STATE_EDGE_B = 91
PROFANTER_RTPS_UDP_OVERHEAD_B = 88  # Profanter et al. (2019) Table II: 188 B UDP payload for 100 B data

# class -> (traffic class / gate index, expected window start us, expected width us)
EXPECTED = {
    "orders":    (3, 0.0, 100.0),
    "dds":       (2, 100.0, 200.0),
    "state":     (1, 300.0, 200.0),
    "telemetry": (0, 500.0, 500.0),
}
# INI keys that carry each class's payload length
PAYLOAD_KEYS = {
    "orders":    "*.fms.app[3..].source.packetLength",
    "dds":       "*.station[*].app[0].source.packetLength",
    "state":     "*.amr[*].app[0].source.packetLength",
    "telemetry": "*.station[*].app[1].source.packetLength",
}
FLEET = (5, 10, 20, 40, 80)
TELEMETRY_INTERVALS_US = (2000.0, 996.0, 747.0, 600.0, 527.0, 472.0, 407.0, 300.0)
N_STATIONS = 4
STATE_HZ, ORDERS_HZ, DDS_HZ = 10.0, 5.0, 100.0


# --------------------------------------------------------------------------- parsing
_UNITS = {"ns": 1e-3, "us": 1.0, "ms": 1e3, "s": 1e6}


def parse_time_us(token: str) -> float:
    """Convert an INI time literal to microseconds for gate arithmetic."""
    m = re.fullmatch(r"\s*([0-9.]+)\s*(ns|us|ms|s)\s*", token)
    if not m:
        raise ValueError(f"cannot parse time {token!r}")
    return float(m.group(1)) * _UNITS[m.group(2)]


def parse_bytes(token: str) -> int:
    """Parse a packet-length literal such as ``1400B``."""
    m = re.fullmatch(r"\s*(\d+)\s*B\s*", token)
    if not m:
        raise ValueError(f"cannot parse byte size {token!r}")
    return int(m.group(1))


def section_lines(text: str, name: str) -> List[str]:
    """Lines of [General] or [Config <name>] with comments stripped (no inheritance)."""
    header = "[General]" if name == "General" else f"[Config {name}]"
    out, inside = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^\[(General|Config\s+\w+)\]", line):
            inside = line.startswith(header)
            continue
        if inside and line and not line.startswith("#"):
            out.append(re.sub(r"\s+#.*$", "", line))
    return out


def parse_gates(text: str, config: str = "Wired_TAS") -> Dict[int, Tuple[List[float], float]]:
    """Read each gate's duration list and phase offset from one config block."""
    lines = section_lines(text, config)
    if not any(re.search(r"transmissionGate\[\*\]\.initiallyOpen\s*=\s*true$", l) for l in lines):
        raise ValueError("expected 'transmissionGate[*].initiallyOpen = true' in the TAS block")
    dur: Dict[int, List[float]] = {}
    off: Dict[int, float] = {}
    for l in lines:
        m = re.search(r"transmissionGate\[(\d+)\]\.(durations|offset)\s*=\s*(.+)$", l)
        if not m:
            continue
        gate, key, val = int(m.group(1)), m.group(2), m.group(3).strip()
        if key == "durations":
            dur[gate] = [parse_time_us(v) for v in val.strip("[]").split(",")]
        else:
            off[gate] = parse_time_us(val)
    missing = sorted(set(dur) ^ set(off))
    if missing or not dur:
        raise ValueError(f"gates without both durations and offset: {missing or 'none found'}")
    return {g: (dur[g], off[g]) for g in dur}


def parse_payloads(text: str) -> Dict[str, int]:
    """Read the configured application payload length for each traffic class."""
    lines = section_lines(text, "General")
    out = {}
    for cls, key in PAYLOAD_KEYS.items():
        hit = [l for l in lines if l.split("=")[0].strip() == key]
        if not hit:
            raise ValueError(f"{key} not found in [General]")
        out[cls] = parse_bytes(hit[-1].split("=", 1)[1])
    return out


# --------------------------------------------------------------------------- arithmetic
def frame_time_us(payload_b: int, tagged: bool, include_phy_ifg: bool = True) -> float:
    """Return serialization time in microseconds.

    When ``include_phy_ifg=True`` (default), includes the 8 B preamble/SFD and 12 B IFG
    (66 B untagged / 70 B tagged). When ``include_phy_ifg=False``, computes the L2
    frame length seen by INET's PeriodicGate (46 B untagged / 50 B tagged).
    """
    base_ovh = OVERHEAD_UNTAGGED_B if include_phy_ifg else L2_OVERHEAD_UNTAGGED_B
    return (payload_b + base_ovh + (TAG_B if tagged else 0)) * 8 / LINK_MBPS


def frames_per_window(width_us: float, payload_b: int, tagged: bool, include_phy_ifg: bool = True) -> int:
    """Count complete frames that fit; fractional frames are excluded."""
    return int(math.floor(width_us / frame_time_us(payload_b, tagged, include_phy_ifg) + TOL))


def max_wire_bytes_for_window(width_us: float) -> int:
    """Largest wire occupancy (bytes) that can finish inside a window of ``width_us``."""
    return int(math.floor(width_us * LINK_MBPS / 8.0 + TOL))


def wagner_order_bytes(n_nodes: int, n_edges: int) -> int:
    """Wagner et al. (2026) Table I Order size estimate: 206 + 154*N_nodes + 434*N_edges."""
    return WAGNER_ORDER_BASE_B + WAGNER_ORDER_NODE_B * n_nodes + WAGNER_ORDER_EDGE_B * n_edges


def wagner_state_bytes(n_nodes: int, n_edges: int) -> int:
    """Wagner et al. (2026) Table I State size estimate: 522 + 75*N_nodes + 91*N_edges."""
    return WAGNER_STATE_BASE_B + WAGNER_STATE_NODE_B * n_nodes + WAGNER_STATE_EDGE_B * n_edges


def window_from_gate(durations_us: List[float], offset_us: float) -> Tuple[float, float, float]:
    """(start, width, cycle) of the open window for initiallyOpen=true, durations=[w, cycle-w]."""
    if len(durations_us) != 2:
        raise ValueError(f"only [open, closed] gates are supported, got {durations_us}")
    cycle = sum(durations_us)
    return (cycle - offset_us) % cycle, durations_us[0], cycle


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def run_checks(ini_text: str) -> Tuple[List[Check], List[str]]:
    gates = parse_gates(ini_text)
    payload = parse_payloads(ini_text)
    checks: List[Check] = []
    report: List[str] = []

    wins, cycle = {}, None
    for cls, (tc, exp_s, exp_w) in EXPECTED.items():
        if tc not in gates:
            checks.append(Check(f"{cls}: gate {tc} defined", False, "missing in Wired_TAS"))
            continue
        s, w, c = window_from_gate(*gates[tc])
        wins[cls] = (s, w)
        cycle = c if cycle is None else cycle
        checks.append(Check(f"{cls}: cycle is {cycle:g} us", abs(c - cycle) < TOL, f"{c:g} us"))
        checks.append(Check(f"{cls}: window [{s:g}, {s + w:g}) us matches intended [{exp_s:g}, {exp_s + exp_w:g})",
                            abs(s - exp_s) < TOL and abs(w - exp_w) < TOL))
        checks.append(Check(f"{cls}: window does not wrap the cycle", s + w <= c + TOL))
    if len(wins) == len(EXPECTED):
        spans = sorted((s, s + w, cls) for cls, (s, w) in wins.items())
        gaps_ok = all(a[1] <= b[0] + TOL for a, b in zip(spans, spans[1:]))
        checks.append(Check("windows are pairwise disjoint", gaps_ok))
        checks.append(Check("windows tile the whole cycle (no dead time)",
                            abs(sum(w for _, w in wins.values()) - cycle) < TOL,
                            f"sum = {sum(w for _, w in wins.values()):g} us"))

    report.append(f"{'class':<10}{'TC':>3}{'payload':>8}{'window us':>16}{'frame us (66/70 B ovh)':>25}"
                  f"{'frames/win':>12}{'latest start us':>17}")
    ceilings = {}
    for cls, (tc, _, _) in EXPECTED.items():
        if cls not in wins:
            continue
        s, w = wins[cls]
        n_u, n_t = frames_per_window(w, payload[cls], False), frames_per_window(w, payload[cls], True)
        n_l2_u = frames_per_window(w, payload[cls], False, include_phy_ifg=False)
        n_l2_t = frames_per_window(w, payload[cls], True, include_phy_ifg=False)
        ceilings[cls] = n_u
        checks.append(Check(f"{cls}: at least one frame fits the window", n_u >= 1 and n_t >= 1))
        checks.append(Check(f"{cls}: frames/window identical with and without C-tag", n_u == n_t,
                            f"untagged {n_u}, tagged {n_t}"))
        if cls == "dds":
            # Known divergence: report both counts instead of asserting equality.
            checks.append(Check("dds: L2 (+46/50 B) vs wire (+66/70 B) accounting differ by exactly one frame "
                                "(documented wire value 9 vs L2-only 10); in-sim confirmation = checklist C8",
                                n_t == 9 and n_l2_t == 10 and n_u == 9 and n_l2_u == 10,
                                f"wire={n_t}, L2={n_l2_t}"))
        else:
            checks.append(Check(f"{cls}: frames/window identical under L2 (+46/50 B) and wire (+66/70 B) accounting",
                                n_u == n_l2_u and n_t == n_l2_t,
                                f"wire={n_t}, L2={n_l2_t}"))
        t_t = frame_time_us(payload[cls], True)
        report.append(f"{cls:<10}{tc:>3}{payload[cls]:>7}B{f'[{s:g}, {s + w:g})':>16}"
                      f"{f'{frame_time_us(payload[cls], False):.2f} / {t_t:.2f}':>25}"
                      f"{n_t:>12}{s + w - t_t:>17.1f}")

    # Evidence-Matrix Validation Checks (traffic_class_evidence_matrix.md)
    if len(wins) == len(EXPECTED):
        mtu_l2_untagged_us = frame_time_us(FULL_MTU_UDP_PAYLOAD_B, False, include_phy_ifg=False)
        mtu_wire_untagged_us = frame_time_us(FULL_MTU_UDP_PAYLOAD_B, False, include_phy_ifg=True)
        mtu_wire_tagged_us = frame_time_us(FULL_MTU_UDP_PAYLOAD_B, True, include_phy_ifg=True)
        checks.append(Check(
            "Full 1500 B IP MTU serialization is 121.44 us (L2) and 123.04/123.36 us (wire), exceeding both 100 us and 120 us windows",
            abs(mtu_l2_untagged_us - 121.44) < 1e-6
            and abs(mtu_wire_untagged_us - 123.04) < 1e-6
            and abs(mtu_wire_tagged_us - 123.36) < 1e-6
            and frames_per_window(wins["orders"][1], FULL_MTU_UDP_PAYLOAD_B, False, include_phy_ifg=False) == 0,
            f"L2={mtu_l2_untagged_us:.2f} us, wire={mtu_wire_untagged_us:.2f}/{mtu_wire_tagged_us:.2f} us > 100 us TC3 window"
        ))
        tc3_max_wire_b = max_wire_bytes_for_window(wins["orders"][1])
        checks.append(Check(
            "TSN guard band (TC3): 100 us window admits at most 1250 B of wire occupancy on eth[1]",
            tc3_max_wire_b == 1250 and 600 + OVERHEAD_UNTAGGED_B <= tc3_max_wire_b,
            f"max_wire={tc3_max_wire_b} B; configured Orders frame = {payload['orders'] + OVERHEAD_UNTAGGED_B} B"))
        # Corrected simple-path (E = N - 1) VDA 5050 arithmetic from traffic_class_evidence_matrix.md
        ord_4_3 = wagner_order_bytes(4, 3)
        ord_20_19 = wagner_order_bytes(20, 19)
        st_3_2 = wagner_state_bytes(3, 2)
        st_3_3 = wagner_state_bytes(3, 3)
        checks.append(Check(
            "VDA 5050 simple-path Order estimates (E=N-1) span 2124 B (4,3) to 11532 B (20,19) and exceed 1500 B IP MTU for N>=3",
            ord_4_3 == 2124 and ord_20_19 == 11532 and wagner_order_bytes(3, 2) == 1536,
            f"Order(3,2)=1536 B, Order(4,3)={ord_4_3} B, Order(20,19)={ord_20_19} B"
        ))
        checks.append(Check(
            "Configured 600 B Orders and 1000 B State lie inside Wagner et al. (2026) low-horizon ranges",
            wagner_order_bytes(1, 0) <= payload["orders"] <= wagner_order_bytes(1, 1)
            and st_3_2 <= payload["state"] <= wagner_state_bytes(4, 3),
            f"Orders={payload['orders']} B in [360, 794] B; State={payload['state']} B in [{st_3_2}, {st_3_3}, 1095] B"
        ))
        checks.append(Check(
            "Configured 200 B DDS surrogate accommodates Profanter et al. (2019) 88 B Fast-RTPS UDP payload overhead",
            payload["dds"] > PROFANTER_RTPS_UDP_OVERHEAD_B,
            f"200 B UDP payload = {payload['dds'] - PROFANTER_RTPS_UDP_OVERHEAD_B} B sample + {PROFANTER_RTPS_UDP_OVERHEAD_B} B Fast-RTPS overhead"
        ))
        # Item 6 & Item 7 checks: Wired FIFO drainage bound vs. D_c and common NER horizon lead time
        fifo_max_drain_us = 80 * frame_time_us(payload["telemetry"], True, include_phy_ifg=True)
        checks.append(Check(
            "Item 6 (Deadline Violation Bound): 80-pkt FIFO max wired drain is 9408.0 us (> 5 ms DDS budget, < 10..100 ms budgets)",
            abs(fifo_max_drain_us - 9408.0) < 1e-6 and 5000.0 < fifo_max_drain_us < 10000.0,
            f"fifo_max_drain={fifo_max_drain_us / 1e3:.3f} ms (causes wired Late_Arrival only for D < 9.408 ms)"
        ))
        checks.append(Check(
            "Item 6 (TDMA Operating Limit): 12 Mbps N=80 superframe (90 ms) satisfies 90 ms min State interarrival and D=100 ms but exceeds D=50 ms",
            40 * 850.0 + 10 * 560.0 <= 42000.0 < 50000.0 and 80 * 850.0 + 39 * 560.0 == 89840.0 < 90000.0,
            "N=40 occupied=39.60 ms <= 42 ms (<50 ms); N=80 occupied=89.84 ms <= 90 ms (>50 ms budget, <=100 ms)"
        ))

    if "telemetry" in wins:
        ceil_mbps = ceilings["telemetry"] * payload["telemetry"] * 8 / (cycle or 1000.0)
        tel_len = payload["telemetry"]
        offered_str = ", ".join(f"{N_STATIONS * tel_len * 8 / i:.1f}" for i in TELEMETRY_INTERVALS_US)
        report.append(f"\ntelemetry payload ceiling under TAS: {ceil_mbps:.1f} Mbps "
                      f"(offered at {len(TELEMETRY_INTERVALS_US)} levels: {offered_str} Mbps)")

    report.append("\nWindow occupancy = offered frames/s over window capacity (frames/window x cycles/s); >100% = queue grows")
    cyc_s = (cycle or 1000.0) * 1e-6
    for cls, rate in (("state", None), ("orders", None)):
        if cls not in ceilings:
            continue
        hz = STATE_HZ if cls == "state" else ORDERS_HZ
        cap = ceilings[cls] / cyc_s
        cells = "  ".join(f"N={n}: {100 * n * hz / cap:.0f}%" for n in FLEET)
        report.append(f"  {cls:<10} (capacity {cap:.0f} frames/s)  {cells}")
    if "dds" in ceilings:
        cap = ceilings["dds"] / cyc_s
        occ = 100 * (N_STATIONS * DDS_HZ) / cap
        report.append(f"  {'dds':<10} (capacity {cap:.0f} frames/s)  {N_STATIONS} stations @ {DDS_HZ:g} Hz: {occ:.1f}%")
    if "telemetry" in ceilings:
        cap = ceilings["telemetry"] / cyc_s
        cells = "  ".join(f"{i:g} us: {100 * (N_STATIONS * 1e6 / i) / cap:.0f}%" for i in TELEMETRY_INTERVALS_US)
        report.append(f"  {'telemetry':<10} (capacity {cap:.0f} frames/s)  {cells}")
    return checks, report


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else Path(__file__).resolve().parents[1] / "simulations" / "omnetpp.ini"
    checks, report = run_checks(path.read_text())
    print("\n".join(report), end="\n\n")
    for c in checks:
        print(f"[{'ok' if c.ok else 'FAIL'}] {c.name}" + (f"  ({c.detail})" if c.detail else ""))
    failed = [c for c in checks if not c.ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

