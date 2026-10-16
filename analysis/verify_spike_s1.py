#!/usr/bin/env python3
"""Strict ScheduledDcf acceptance checks at nominal and worst-case points."""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import (
    OMNETPP_ENV_STR as OMNETPP_ENV,
    INET_ROOT_STR as INET_ROOT,
    MATRIXFACTORY_LIB_STR as MATRIXFACTORY_LIB,
    SIM_DIR_STR as SIM_DIR,
)

RES_ROOT = Path(SIM_DIR) / "results" / "verify_spike_s1"


def extract_scalars(path):
    scalars = {}
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith("scalar "):
                continue
            parts = line.strip().split()
            if len(parts) >= 4:
                try:
                    scalars[f"{parts[1]} {' '.join(parts[2:-1]).strip(chr(34))}"] = float(parts[-1])
                except ValueError:
                    pass
    return scalars


def run_sim(config, n_amrs, phy_rate, sim_time="10s"):
    run_dir = RES_ROOT / f"{config}_N{n_amrs}_{phy_rate}Mbps"
    run_dir.mkdir(parents=True, exist_ok=True)
    for path in run_dir.iterdir():
        if path.is_file() and path.suffix in {".sca", ".vec", ".vci", ".elog"}:
            path.unlink()
    cmd = (
        f"source {OMNETPP_ENV} && export INET_ROOT={INET_ROOT} && cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. -l $INET_ROOT/src/INET "
        f"-l {MATRIXFACTORY_LIB} -c {config} -u Cmdenv omnetpp.ini "
        f"'--*.numAmrs={n_amrs}' '--*.fms.numApps={3 + n_amrs}' "
        f"'--*.wirelessPhyRate={phy_rate}Mbps' "
        f"'--**.wlan[*].bitrate={phy_rate}Mbps' '--sim-time-limit={sim_time}' "
        f"'--**.simTimeLimit={sim_time}' '--warmup-period=0s' '--**.warmupTime=0s' "
        f"'--result-dir={run_dir}'"
    )
    result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{config} N={n_amrs} PHY={phy_rate} failed:\n{result.stderr}")
    files = list(run_dir.glob("*.sca"))
    if len(files) != 1:
        raise RuntimeError(f"expected one scalar file in {run_dir}, found {len(files)}")
    return extract_scalars(files[0]), extract_parameters(files[0])


def extract_parameters(path):
    parameters = {}
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith("par "):
                continue
            parts = line.strip().split(maxsplit=3)
            if len(parts) == 4:
                parameters[f"{parts[1]} {parts[2]}"] = parts[3]
    return parameters


def sum_exact(scalars, statistic):
    suffix = f" {statistic}"
    matches = [value for key, value in scalars.items() if key.endswith(suffix)]
    if not matches:
        raise RuntimeError(f"required scalar {statistic!r} is absent")
    return int(sum(matches))


def required(scalars, key):
    if key not in scalars:
        raise RuntimeError(f"required scalar {key!r} is absent")
    return scalars[key]


def seconds(parameters, key):
    if key not in parameters or not parameters[key].endswith("s"):
        raise RuntimeError(f"required time parameter {key!r} is absent")
    return float(parameters[key][:-1])


def check_scheduled(label, result, max_delay_bound_ms, expected):
    scalars, parameters = result
    retries = sum_exact(scalars, "packetSentToPeerWithRetry:count")
    retry_drops = sum_exact(scalars, "retryLimitReached:count")
    transmitted = sum_exact(scalars, "packetSentToPeer:count")
    maximum = required(scalars, "MatrixFactoryNetwork.fms.app[0].sink ecdf_q_1.000")
    granted = sum_exact(scalars, "scheduledDcf_numGrantedInSlot")
    actual = {
        "state_slot": seconds(parameters, "MatrixFactoryNetwork.amr[0].wlan[0].mac.dcf slotDuration"),
        "orders_slot": seconds(parameters, "MatrixFactoryNetwork.ap.wlan[0].mac.dcf slotDuration"),
        "superframe": seconds(parameters, "MatrixFactoryNetwork.ap.wlan[0].mac.dcf superframeDuration"),
    }
    for name, wanted in expected.items():
        if abs(actual[name] - wanted) > 1e-12:
            raise RuntimeError(f"{label}: {name}={actual[name]} s, expected {wanted} s")
    if transmitted <= 0 or granted <= 0:
        raise RuntimeError(f"{label}: scheduled traffic/grants are absent")
    if retries != 0 or retry_drops != 0:
        raise RuntimeError(f"{label}: retries={retries}, retry-limit drops={retry_drops}")
    if maximum > max_delay_bound_ms:
        raise RuntimeError(f"{label}: State maximum {maximum:.3f} ms exceeds {max_delay_bound_ms:.3f} ms")
    print(f"[ok] {label}: tx={transmitted}, retries=0, retry drops=0, State max={maximum:.3f} ms")


def main():
    print("ScheduledDcf strict acceptance")
    nominal = run_sim("Cell2", 40, 54)
    worst_case = run_sim("Cell2", 80, 12)
    csma = run_sim("Cell1", 40, 54)

    check_scheduled("N=40, 54 Mbps", nominal, 25.0,
                    {"state_slot": 0.0004, "orders_slot": 0.0004, "superframe": 0.020})
    check_scheduled("N=80, 12 Mbps", worst_case, 95.0,
                    {"state_slot": 0.00085, "orders_slot": 0.00056, "superframe": 0.090})
    csma_retries = sum_exact(csma[0], "packetSentToPeerWithRetry:count")
    if csma_retries <= 0:
        raise RuntimeError("CSMA control has no retry activity; scheduled contrast is not established")
    print(f"[ok] CSMA control retry count is nonzero ({csma_retries})")
    print("all ScheduledDcf acceptance checks passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
