#!/usr/bin/env python3
"""Run 802.11 INET calibration across 54, 24, 12, and 6 Mbps (Checklist C5).

Runs an unloaded single-AMR Cell 1 baseline and extracts exact frameSequenceDuration
for State (1000 B uplink) and Orders (600 B downlink) from OMNeT++ scalar files.
"""

import os
import subprocess
import sys
import re
from pathlib import Path

# Ensure analysis directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import OMNETPP_ENV_STR as OMNETPP_ENV, INET_ROOT_STR as INET_ROOT, PROJECT_ROOT_STR as PROJECT_ROOT, SIM_DIR_STR as SIM_DIR

RATES = ["54Mbps", "24Mbps", "12Mbps", "6Mbps"]

def run_calibration():
    results = {}
    for rate in RATES:
        print(f"[*] Running Cell1 calibration at {rate}...")
        cmd = (
            f"source {OMNETPP_ENV} && "
            f"export INET_ROOT={INET_ROOT} && "
            f"cd {SIM_DIR} && "
            f"opp_run -n $INET_ROOT/src:../src:. "
            f"-l $INET_ROOT/src/INET -l ../out/gcc-release/matrixfactory "
            f"-c Cell1 -u Cmdenv "
            f"'--*.numAmrs=1' '--*.numStations=0' '--*.fms.numApps=4' "
            f"'--**.wlan[*].bitrate={rate}' "
            f"'--sim-time-limit=10s' '--**.warmupTime=0s' "
            f"'--**.frameSequenceDuration.result-recording-modes=+min,+max,+mean' "
            f"omnetpp.ini"
        )
        res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[!] Error running {rate}: {res.stderr}")
            sys.exit(1)

        # Find the latest .sca file in simulations/results
        res_dir = os.path.join(SIM_DIR, "results")
        sca_files = [os.path.join(res_dir, f) for f in os.listdir(res_dir) if f.endswith(".sca")]
        latest_sca = max(sca_files, key=os.path.getmtime)

        state_dur = None
        orders_dur = None
        with open(latest_sca, "r") as f:
            for line in f:
                if "amr[0].wlan[0].mac.dcf" in line and "frameSequenceDuration:mean" in line:
                    parts = line.strip().split()
                    state_dur = float(parts[-1]) * 1e6  # us
                elif "ap.wlan[0].mac.dcf" in line and "frameSequenceDuration:mean" in line:
                    parts = line.strip().split()
                    orders_dur = float(parts[-1]) * 1e6  # us

        results[rate] = {
            "state_seq_us": state_dur,
            "orders_seq_us": orders_dur
        }
        print(f"  [+] {rate}: State sequence = {state_dur:.2f} us, Orders sequence = {orders_dur:.2f} us")

    return results

if __name__ == "__main__":
    results = run_calibration()
    print("\n=== Calibration Summary Table ===")
    print(f"{'PHY Rate':<10} | {'State Seq (us)':<15} | {'State + DIFS (us)':<18} | {'Orders Seq (us)':<16} | {'Orders + DIFS (us)':<19}")
    print("-" * 88)
    for r, data in results.items():
        s = data['state_seq_us']
        o = data['orders_seq_us']
        s_difs = s + 28.0
        o_difs = o + 28.0
        print(f"{r:<10} | {s:<15.2f} | {s_difs:<18.2f} | {o:<16.2f} | {o_difs:<19.2f}")
