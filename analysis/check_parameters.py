#!/usr/bin/env python3
"""Verification script to check consistency between simulations/omnetpp.ini and docs/parameters.md.

Detects parameter drift between configuration and documentation sheets.
Usage:
    python3 analysis/check_parameters.py
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INI_PATH = REPO_ROOT / "simulations" / "omnetpp.ini"
PARAMS_MD_PATH = REPO_ROOT / "docs" / "parameters.md"

def parse_ini_sections(ini_file):
    """Parse INI entries into {(section, key): value} with continuation-line support."""
    kv = {}
    section = "General"
    lines = ini_file.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].split("#", 1)[0].strip()
        i += 1
        if not line:
            continue
        m = re.match(r"^\[(?:Config\s+)?(\w+)\]$", line)
        if m:
            section = m.group(1)
            continue
        while line.endswith("\\") and i < len(lines):
            line = line[:-1].rstrip() + " " + lines[i].split("#", 1)[0].strip()
            i += 1
        if "=" in line:
            k, v = line.split("=", 1)
            kv[(section, k.strip())] = v.strip()
    return kv

def check_parameters():
    print(f"[*] Checking {INI_PATH.relative_to(REPO_ROOT)} against {PARAMS_MD_PATH.relative_to(REPO_ROOT)}...")
    if not INI_PATH.exists():
        print(f"[!] Error: {INI_PATH} not found.")
        sys.exit(1)
    if not PARAMS_MD_PATH.exists():
        print(f"[!] Error: {PARAMS_MD_PATH} not found.")
        sys.exit(1)

    ini_kv = parse_ini_sections(INI_PATH)
    params_text = PARAMS_MD_PATH.read_text(encoding="utf-8")

    # (section, key, expected_ini_value, doc_regex_pattern)
    critical_checks = [
        ("General", "sim-time-limit", "60s", r"`sim-time-limit`\s*\|\s*`60`"),
        ("General", "warmup-period", "5s", r"`warmup-period`\s*\|\s*`5`"),
        ("General", "num-rngs", "3", r"`num-rngs`\s*\|\s*`3`"),
        ("Sweep", "repeat", "22", r"`repeat`\s*\|\s*`22`"),
        ("Point", "*.numAmrs", "${nAmr=10}", r"`\*\.numAmrs`\s*\|\s*`10`"),
        ("Sweep", "*.numAmrs", "${nAmr=5, 10, 20, 40, 80}", r"`5,\s*10,\s*20,\s*40,\s*80`"),
        ("Sweep", "*.wirelessPhyRate", "${phyRate=54Mbps, 12Mbps}", r"Sweep:\s*`54,\s*12`"),
        ("General", "*.amr[*].app[0].source.packetLength", "1000B", r"State.*`1000`\s*B"),
        ("General", "*.fms.app[3..].source.packetLength", "600B", r"Orders.*`600`\s*B"),
        ("General", "*.station[*].app[0].source.packetLength", "200B", r"DDS.*`200`\s*B"),
        ("General", "*.station[*].app[1].source.packetLength", "1400B", r"Telemetry.*`1400`\s*B"),
        ("Wired_FIFO", "**.tsnSwitch.eth[*].macLayer.queue.packetCapacity", "80", r"`DropTailQueue`\s*\|\s*`80`\s*packets"),
        ("Wired_Prio", "**.tsnSwitch.eth[*].macLayer.queue.queue[*].packetCapacity", "20", r"`20`\s*packets\s*/\s*class"),
        ("Wired_TAS", "**.tsnSwitch.eth[*].macLayer.queue.queue[*].packetCapacity", "20", r"`20`\s*packets\s*/\s*class"),
    ]

    all_passed = True
    for section, key, expected_ini, pattern in critical_checks:
        val = ini_kv.get((section, key))
        ini_ok = (val == expected_ini)
        doc_ok = bool(re.search(pattern, params_text))
        if ini_ok and doc_ok:
            print(f"  [+] Verified [{section}] {key} = {val}")
        else:
            print(f"  [-] Mismatch [{section}] {key}: INI={val!r} (expected {expected_ini!r}), doc_match={doc_ok}")
            all_passed = False

    if all_passed:
        print("[✓] Consistency check passed: all checked baseline parameters are documented in docs/parameters.md.")
    else:
        print("[!] Some parameter mismatches or missing entries detected.")
        return False
    return True

if __name__ == "__main__":
    sys.exit(0 if check_parameters() else 1)
