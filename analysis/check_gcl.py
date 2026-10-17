"""Check the 802.1Qbv gate schedule in simulations/omnetpp.ini against the wire arithmetic.

Reads ``[Config Wired_TAS]`` (gate durations/offsets) and the application packet
lengths from the INI, then verifies the facts documented as "Verified (analytic)"
in docs/parameters.md section 8 and docs/decisions.md section 6:

* the four windows are disjoint, inside the cycle and the durations add up to the cycle;
* the windows match the intended schedule (Orders [0,100), DDS [100,300), State
  [300,500), Telemetry [500,1000) us), using the convention of the INI comment:
  durations=[w, cycle-w], initiallyOpen=true, offset = cycle - start (mod cycle);
* frames per window (INET's implicit guard band: a frame must finish inside the
  window), identical with and without the 4 B C-tag;
* the telemetry payload ceiling (4 x 1400 B per 1 ms = 44.8 Mbps);
* the latest in-window start time of one frame (State: 500 - 85.6 = 414.4 us, checklist C6);
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
OVERHEAD_UNTAGGED_B = 66            # UDP 8 + IP 20 + MAC 14 + FCS 4 + preamble/SFD 8 + IFG 12
TAG_B = 4                           # 802.1Q C-tag
TOL = 1e-9

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
    # Read assignments local to the requested block; this checker does not resolve INI inheritance.
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
def frame_time_us(payload_b: int, tagged: bool) -> float:
    """Return serialization time including frame overhead and optional C-tag."""
    return (payload_b + OVERHEAD_UNTAGGED_B + (TAG_B if tagged else 0)) * 8 / LINK_MBPS


def frames_per_window(width_us: float, payload_b: int, tagged: bool) -> int:
    """Count complete frames that fit; fractional frames are excluded."""
    return int(math.floor(width_us / frame_time_us(payload_b, tagged) + TOL))


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
        ceilings[cls] = n_u
        checks.append(Check(f"{cls}: at least one frame fits the window", n_u >= 1 and n_t >= 1))
        checks.append(Check(f"{cls}: frames/window identical with and without C-tag", n_u == n_t,
                            f"untagged {n_u}, tagged {n_t}"))
        t_t = frame_time_us(payload[cls], True)
        report.append(f"{cls:<10}{tc:>3}{payload[cls]:>7}B{f'[{s:g}, {s + w:g})':>16}"
                      f"{f'{frame_time_us(payload[cls], False):.2f} / {t_t:.2f}':>25}"
                      f"{n_t:>12}{s + w - t_t:>17.1f}")

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
