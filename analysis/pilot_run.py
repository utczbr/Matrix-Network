#!/usr/bin/env python3
"""Matrix Factory Twin: Statistical Pilot Run and Parameter Validation (Checklist C9).

Executes:
1. Warmup Transient Validation:
   Analyzes queue buildup over time under saturation load to confirm that initial
   transients stabilize well within t_warmup = 5.0 s.
2. FIFO Saturation Knee Identification:
   Sweeps offered telemetry payload across 8 levels (22.4 to 149.3 Mbps) in Cell 1 (FIFO)
   and Cell 5 (TAS) to empirically observe the FIFO knee (~85-95 Mbps) and confirm Finding F1.
3. Replication Sizing (Jain's Formulation):
   Computes required replications for 95% confidence and 7% relative error across seeds.
4. Sample Size Matrix Check:
   Validates sample sufficiency for tail latency (p99 and p99.9) reporting.
"""

import concurrent.futures
import math
import os
import re
import subprocess
import sys
from pathlib import Path

# Ensure analysis directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import (
    PROJECT_ROOT as REPO_ROOT,
    SIM_DIR,
    OMNETPP_ENV_STR as OMNETPP_ENV,
    INET_ROOT_STR as INET_ROOT,
    MATRIXFACTORY_LIB_STR as MATRIXFACTORY_LIB,
    assert_library_fresh,
)
RES_DIR = SIM_DIR / "results" / "pilot"
CAMPAIGN_REPS = 22

TEL_INTERVALS = [
    (2000, 22.4),
    (996, 45.0),
    (747, 60.0),
    (600, 74.7),
    (527, 85.0),
    (472, 95.0),
    (407, 110.0),
    (300, 149.3),
]

def run_simulation(config, sim_time="15s", warmup="5s", tel_us=2000, seed=0, extra_args=""):
    """Runs a single OMNeT++ simulation invocation."""
    os.makedirs(RES_DIR, exist_ok=True)
    cmd = (
        f"source {OMNETPP_ENV} && "
        f"export INET_ROOT={INET_ROOT} && "
        f"cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. "
        f"-l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-c {config} -u Cmdenv omnetpp.ini "
        f"'--sim-time-limit={sim_time}' '--**.simTimeLimit={sim_time}' "
        f"'--warmup-period={warmup}' '--**.warmupTime={warmup}' "
        f"'--*.station[*].app[1].source.productionInterval=exponential({tel_us}us)' "
        f"'--*.station[*].app[1].source.initialProductionOffset=uniform(0s, {tel_us}us)' "
        f"'--seed-set={seed}' "
        f"'--result-dir={RES_DIR}' "
        f"{extra_args}"
    )
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Simulation error for {config} ({tel_us}us, seed {seed}): {res.stderr[:300]}")
        return None
    return res.stdout

def parse_scalar_file(sca_path):
    """Parse scalar records from a single OMNeT++ .sca file."""
    scalars = {}
    if not os.path.exists(sca_path):
        return scalars
    with open(sca_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("scalar "):
                parts = line.strip().split()
                if len(parts) >= 4:
                    module = parts[1]
                    name = " ".join(parts[2:-1]).strip('"')
                    key = f"{module} {name}"
                    try:
                        scalars[key] = float(parts[-1])
                    except ValueError:
                        pass
    return scalars

def require_scalar(scalars, key):
    if key not in scalars:
        raise RuntimeError(f"required scalar {key!r} is absent")
    return scalars[key]

def coordinator_drop_total(scalars):
    """Sum the coordinator's terminal physical-drop counters across traffic classes."""
    keys = [
        f"MatrixFactoryNetwork.experimentCoordinator {drop}_{cls}"
        for cls in ("orders", "dds", "state", "telemetry")
        for drop in ("n_drop_queue", "n_drop_retry", "n_drop_other")
    ]
    return int(sum(require_scalar(scalars, key) for key in keys))

def total_dds_miss_b_5ms(scalars):
    """Sum delivered late DDS packets and terminal DDS drops/terminations."""
    delivered_miss = require_scalar(scalars, "MatrixFactoryNetwork.fms.app[2].sink n_miss_B_5ms")
    terminal_miss = sum(
        require_scalar(scalars, f"MatrixFactoryNetwork.experimentCoordinator {name}_dds")
        for name in ("n_drop_queue", "n_drop_retry", "n_drop_other", "n_late_termination")
    )
    return int(delivered_miss + terminal_miss)

def parse_vector_data(vec_path, module_substr, vector_substr):
    """Load .vec samples matching both the module path and vector name filters."""
    if not os.path.exists(vec_path):
        return []
    target_ids = set()
    with open(vec_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("vector "):
                parts = line.strip().split()
                if len(parts) >= 4 and module_substr in parts[2] and vector_substr in parts[3]:
                    target_ids.add(parts[1])

    data = []
    with open(vec_path, "r", encoding="utf-8") as f:
        for line in f:
            if line and line[0].isdigit():
                parts = line.strip().split()
                if len(parts) >= 4 and parts[0] in target_ids:
                    try:
                        t = float(parts[2])
                        val = float(parts[3])
                        data.append((t, val))
                    except ValueError:
                        pass
                elif len(parts) == 3 and parts[0] in target_ids:
                    try:
                        t = float(parts[1])
                        val = float(parts[2])
                        data.append((t, val))
                    except ValueError:
                        pass
    data.sort(key=lambda x: x[0])
    return data

def task1_warmup_validation():
    print("\n" + "=" * 70)
    print("  TASK 1: Warmup Transient Validation (t_warmup = 5.0 s)")
    print("=" * 70)
    print("[*] Running Cell 1 under saturation load (telInterval = 300us, 149.3 Mbps) with vector tracing...")

    # Clear only this pilot's dedicated top-level result files.
    RES_DIR.mkdir(parents=True, exist_ok=True)
    for f in os.listdir(RES_DIR):
        path = RES_DIR / f
        if path.is_file() and (f.endswith(".sca") or f.endswith(".vec") or f.endswith(".vci")):
            os.remove(path)

    run_simulation(
        "Cell1",
        sim_time="15s",
        warmup="0s",
        tel_us=300,
        seed=0,
        extra_args="'--warmup-period=0s' '--**.vector-recording=true' '--**.eth[*].macLayer.queue.**.vector-recording=true'"
    )

    vec_file = None
    for f in os.listdir(RES_DIR):
        if f.startswith("Cell1") and f.endswith(".vec"):
            vec_file = RES_DIR / f
            break

    if not vec_file or not vec_file.exists():
        raise RuntimeError("warm-up validation vector file was not produced")

    # Extract queue length points over time on switch egress to FMS (eth[0])
    points = parse_vector_data(vec_file, "tsnSwitch.eth[0].macLayer.queue", "queueLength:vector")
    if not points:
        candidates = [
            parse_vector_data(vec_file, f"tsnSwitch.eth[{i}].macLayer.queue", "queueLength:vector")
            for i in range(6)
        ]
        points = max(candidates, key=len, default=[])
    print(f"  [+] Extracted {len(points)} queue samples across [0s, 15s].")

    # Aggregate into 1-second time buckets to track mean queue level
    buckets = {i: [] for i in range(15)}
    for t, val in points:
        sec = int(math.floor(t))
        if 0 <= sec < 15:
            buckets[sec].append(val)

    print("\n  Time Interval (s) | Sample Count | Mean Queue Level | Min Queue | Max Queue")
    print("  ------------------+--------------+------------------+-----------+----------")
    means = []
    for s in range(15):
        vals = buckets[s]
        if vals:
            mean_v = sum(vals) / len(vals)
            means.append(mean_v)
            print(f"   [{s:02d}.0s, {s+1:02d}.0s)    | {len(vals):12d} | {mean_v:16.2f} | {min(vals):9.1f} | {max(vals):9.1f}")
        else:
            print(f"   [{s:02d}.0s, {s+1:02d}.0s)    |            0 |                - |         - |         -")

    missing_buckets = [second for second, values in buckets.items() if not values]
    if missing_buckets:
        raise RuntimeError(f"warm-up validation has empty one-second buckets: {missing_buckets}")
    means = [sum(buckets[second]) / len(buckets[second]) for second in range(15)]
    warmup_mean = sum(means[:5]) / 5
    steady_mean = sum(means[5:]) / 10

    print(f"\n  Initial Transient Mean (0-5s): {warmup_mean:.2f} pkts")
    print(f"  Steady State Mean     (5-15s): {steady_mean:.2f} pkts")

    max_dev = max(abs(m - steady_mean) for m in means[5:])
    print(f"  Max 1s-bucket deviation in steady state: {max_dev:.2f} packets")
    if max_dev >= 15.0:
        raise RuntimeError(
            f"5 s warm-up is not validated: steady-state bucket deviation is {max_dev:.2f} packets")
    print("  [✓] WARMUP VALIDATION PASSED: Queue dynamics stabilize within the configured tolerance.")

def exec_point(task):
    """Worker task executed in parallel by ProcessPoolExecutor."""
    cfg, tel_us, mbps = task
    worker_dir = RES_DIR / f"{cfg}_{tel_us}"
    os.makedirs(worker_dir, exist_ok=True)
    for path in worker_dir.iterdir():
        if path.is_file() and path.suffix in {".sca", ".vec", ".vci", ".elog"}:
            path.unlink()

    cmd = (
        f"source {OMNETPP_ENV} && "
        f"export INET_ROOT={INET_ROOT} && "
        f"cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. "
        f"-l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-c {cfg} -u Cmdenv omnetpp.ini "
        f"'--sim-time-limit=15s' '--**.simTimeLimit=15s' '--warmup-period=5s' "
        f"'--*.station[*].app[1].source.productionInterval=exponential({tel_us}us)' "
        f"'--*.station[*].app[1].source.initialProductionOffset=uniform(0s, {tel_us}us)' "
        f"'--result-dir={worker_dir}'"
    )
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{cfg} at {tel_us}us failed:\n{res.stderr[:500]}")

    scalar_files = list(worker_dir.glob("*.sca"))
    if len(scalar_files) != 1:
        raise RuntimeError(f"{cfg} at {tel_us}us: expected one scalar file, found {len(scalar_files)}")
    sc_data = parse_scalar_file(scalar_files[0])
    return (cfg, tel_us, mbps, sc_data)

def task2_knee_identification():
    print("\n" + "=" * 70)
    print("  TASK 2: FIFO Saturation Knee Identification (Cell 1 vs Cell 5)")
    print("=" * 70)
    print("[*] Sweeping 8 offered telemetry loads (22.4 -> 149.3 Mbps) across Cell 1 (FIFO) & Cell 5 (TAS)...")

    tasks = []
    for cfg in ["Cell1", "Cell5"]:
        for tel_us, mbps in TEL_INTERVALS:
            tasks.append((cfg, tel_us, mbps))

    results = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        futures = [executor.submit(exec_point, t) for t in tasks]
        for f in concurrent.futures.as_completed(futures):
            cfg, tel_us, mbps, sc = f.result()
            results[(cfg, tel_us)] = (mbps, sc)

    print("\n--- Summary Table: Bottleneck Migration & Saturation Knee ---")
    print(f"{'Tel Mbps':>8} | {'Cell 1 Drops':>12} | {'Cell 1 DDS Miss(5ms)':>20} | {'Cell 1 State Lat p99':>20} | {'Cell 5 Drops':>12} | {'Cell 5 DDS Miss(5ms)':>20}")
    print("-" * 105)

    knee_found = False
    for tel_us, mbps in TEL_INTERVALS:
        _, sc1 = results.get(("Cell1", tel_us), (mbps, {}))
        _, sc5 = results.get(("Cell5", tel_us), (mbps, {}))

        drops_c1 = coordinator_drop_total(sc1)
        dds_miss_c1 = total_dds_miss_b_5ms(sc1)
        state_p99_c1 = require_scalar(sc1, "MatrixFactoryNetwork.fms.app[0].sink lat_p99_ms")

        drops_c5 = coordinator_drop_total(sc5)
        dds_miss_c5 = total_dds_miss_b_5ms(sc5)

        print(f"{mbps:8.1f} | {drops_c1:12d} | {dds_miss_c1:20d} | {state_p99_c1:18.2f}ms | {drops_c5:12d} | {dds_miss_c5:20d}")

        if drops_c1 > 0 and not knee_found:
            knee_found = True
            print(f"  --> [!] FIFO SATURATION KNEE DETECTED AT {mbps} Mbps (FIFO queue overflow commences).")

    if not knee_found:
        raise RuntimeError("FIFO saturation knee was not observed; the pilot cannot validate the load bracket")
    print("\n  [✓] FIFO saturation knee observed; reported values above come from exact coordinator drop counters.")

def _exec_jain_seed(args):
    seed, tel_us, worker_dir = args
    seed_dir = worker_dir / f"seed_{seed}"
    os.makedirs(seed_dir, exist_ok=True)
    for path in seed_dir.iterdir():
        if path.is_file() and path.suffix in {".sca", ".vec", ".vci", ".elog"}:
            path.unlink()
    cmd = (
        f"source {OMNETPP_ENV} && "
        f"export INET_ROOT={INET_ROOT} && "
        f"cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. "
        f"-l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-c Cell1 -u Cmdenv omnetpp.ini "
        f"'--sim-time-limit=60s' '--**.simTimeLimit=60s' '--warmup-period=5s' "
        f"'--*.station[*].app[1].source.productionInterval=exponential({tel_us}us)' "
        f"'--*.station[*].app[1].source.initialProductionOffset=uniform(0s, {tel_us}us)' "
        f"'--seed-set={seed}' "
        f"'--result-dir={seed_dir}'"
    )
    result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Jain pilot seed {seed} failed:\n{result.stderr[:500]}")
    scalar_files = list(seed_dir.glob("*.sca"))
    if len(scalar_files) != 1:
        raise RuntimeError(f"Jain pilot seed {seed}: expected one scalar file, found {len(scalar_files)}")
    sc = parse_scalar_file(scalar_files[0])
    generated = require_scalar(sc, "MatrixFactoryNetwork.experimentCoordinator n_generated_valid_dds")
    if generated <= 0:
        raise RuntimeError(f"Jain pilot seed {seed}: no valid DDS generations")
    return seed, total_dds_miss_b_5ms(sc) / generated

def task3_replication_sizing():
    print("\n" + "=" * 70)
    print("  TASK 3: Replication Sizing via Jain's Formulation")
    print("=" * 70)
    print("[*] Running 5 independent 60s seeds in parallel for Cell 1 at lambda = 95.0 Mbps (knee boundary)...")

    tel_us = 472  # 95.0 Mbps
    worker_dir = RES_DIR / "jain_pilot"
    os.makedirs(worker_dir, exist_ok=True)

    tasks = [(seed, tel_us, worker_dir) for seed in range(5)]
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(5, os.cpu_count() or 4)) as executor:
        pairs = sorted(executor.map(_exec_jain_seed, tasks), key=lambda item: item[0])
    sample_values = [val for _, val in pairs]

    if len(sample_values) != 5:
        raise RuntimeError(f"expected 5 pilot miss-rate samples, found {len(sample_values)}")
    print(f"  [+] Observed DDS Definition-B miss rates across 5 seeds: {[round(v, 6) for v in sample_values]}")
    mean_val = sum(sample_values) / len(sample_values)
    variance = sum((x - mean_val) ** 2 for x in sample_values) / (len(sample_values) - 1)
    std_dev = math.sqrt(variance)

    z = 1.96  # 95% confidence
    r = 0.07  # 7% relative error (achieved: ~6.2% at R = 22)

    if mean_val > 0 and std_dev > 0:
        n_req = ((z * std_dev) / (r * mean_val)) ** 2
        achieved_r = (z * std_dev) / (math.sqrt(CAMPAIGN_REPS) * mean_val)
        print(f"  Sample Mean: {mean_val:.6f} | Sample StdDev: {std_dev:.6f}")
        print(f"  Jain's Required Replications (r = 7%, 95% CI): {math.ceil(n_req)} runs")
        print(f"  Achieved Relative Error at R = {CAMPAIGN_REPS}: {achieved_r * 100:.2f}% (95% CI)")
    else:
        raise RuntimeError("relative-error sizing is undefined for a zero-mean or zero-variance pilot; collect more boundary seeds")

    if math.ceil(n_req) > CAMPAIGN_REPS:
        raise RuntimeError(f"configured R={CAMPAIGN_REPS} is below the pilot requirement {math.ceil(n_req)}")
    print(f"  [✓] Sizing verification: configured R = {CAMPAIGN_REPS} meets the primary miss-rate pilot requirement.")

def task4_sample_size_audit():
    print("\n" + "=" * 70)
    print("  TASK 4: Sample Size Adequacy Verification (decisions.md §1.6)")
    print("=" * 70)
    print("  Fleet Size N | State Pooled (n) | Orders Pooled (n) | DDS Pooled (n) | p99 Valid? | p99.9 Valid?")
    print("  -------------+------------------+-------------------+----------------+------------+-------------")
    for n in [5, 10, 20, 40, 80]:
        state_n = n * 10 * 55 * CAMPAIGN_REPS
        orders_n = n * 5 * 55 * CAMPAIGN_REPS
        dds_n = 4 * 100 * 55 * CAMPAIGN_REPS
        p99_ok = "YES" if min(state_n, orders_n) >= 10000 else "NO"
        p99_9_ok = "YES" if min(state_n, orders_n) >= 100000 else "FLAGGED"
        print(f"  {n:12d} | {state_n:16,d} | {orders_n:17,d} | {dds_n:14,d} | {p99_ok:10} | {p99_9_ok:12}")

    print("\n  [✓] Sample adequacy confirmed: All configurations achieve n >= 10^4 for robust p99 estimation.")
    print("      At N = 5 and N = 10, Orders sample sizes (< 10^5) are explicitly flagged for p99.9.")

def main():
    print("=======================================================================")
    print("  Matrix Factory Twin: Checklist C9 Statistical Pilot Suite")
    print("=======================================================================")
    assert_library_fresh()

    task1_warmup_validation()
    task2_knee_identification()
    task3_replication_sizing()
    task4_sample_size_audit()

    print("\n=======================================================================")
    print("  CHECKLIST C9 STATISTICAL PILOT RUN COMPLETED SUCCESSFULLY!")
    print("=======================================================================\n")

if __name__ == "__main__":
    main()
