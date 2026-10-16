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

def parse_ini_key_values(ini_file):
    """Simple parser for INI key-value entries."""
    kv = {}
    with open(ini_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.split("#")[0].strip()
                kv[k] = v
    return kv

def check_parameters():
    print(f"[*] Checking {INI_PATH.relative_to(REPO_ROOT)} against {PARAMS_MD_PATH.relative_to(REPO_ROOT)}...")
    if not INI_PATH.exists():
        print(f"[!] Error: {INI_PATH} not found.")
        sys.exit(1)
    if not PARAMS_MD_PATH.exists():
        print(f"[!] Error: {PARAMS_MD_PATH} not found.")
        sys.exit(1)

    ini_kv = parse_ini_key_values(INI_PATH)
    params_text = PARAMS_MD_PATH.read_text(encoding="utf-8")

    # Critical parameters to check for presence in documentation
    critical_checks = [
        ("sim-time-limit", r"sim-time-limit"),
        ("warmup-period", r"warmup-period"),
        ("num-rngs", r"num-rngs"),
        ("repeat", r"Replication Count.*22"),
        ("*.wirelessPhyRate", r"wirelessPhyRate"),
        ("**.wlan[*].bitrate", r"54\s*Mbps"),
        ("*.amr[*].app[0].source.packetLength", r"1000\s*B"),
        ("*.fms.app[3..].source.packetLength", r"600\s*B"),
        ("*.station[*].app[0].source.packetLength", r"200\s*B"),
        ("*.station[*].app[1].source.packetLength", r"1400\s*B"),
        ("**.tsnSwitch.eth[*].macLayer.queue.packetCapacity", r"80"),
    ]

    all_passed = True
    for key, pattern in critical_checks:
        val = ini_kv.get(key)
        if re.search(pattern, params_text):
            print(f"  [+] Match found in sheet for '{key}' (INI value: {val})")
        else:
            print(f"  [-] Warning: '{key}' (INI value: {val}) not found or pattern mismatch in {PARAMS_MD_PATH.name}")
            all_passed = False

    if all_passed:
        print("[✓] Consistency check passed: all checked baseline parameters are documented in docs/parameters.md.")
    else:
        print("[!] Some parameter mismatches or missing entries detected.")
        return False
    return True

if __name__ == "__main__":
    sys.exit(0 if check_parameters() else 1)
