#!/usr/bin/env python3
"""Execute Checklist C8: Execution Rigor & Validation Suite.

Verifies:
1. AMR Spatial Placement Independence (RNG stream isolation, rng-2 vs rng-0).
2. Offered Load Parity across Cells 1, 3, 5 (traffic source isolation, rng-1).
3. GCL Gate State Timing in Cell 5 (exact microsecond window alignment).
4. Packet Conservation Accounting in DeadlineSink.
"""

import os
import subprocess
import sys
import re
from pathlib import Path

# Ensure analysis directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import (
    OMNETPP_ENV_STR as OMNETPP_ENV,
    INET_ROOT_STR as INET_ROOT,
    MATRIXFACTORY_LIB_STR as MATRIXFACTORY_LIB,
    PROJECT_ROOT_STR as PROJECT_ROOT,
    SIM_DIR_STR as SIM_DIR,
)
RES_DIR = os.path.join(SIM_DIR, "results", "verify_c8")

def run_simulation(config, sim_time="10s", extra_args=""):
    os.makedirs(RES_DIR, exist_ok=True)
    cmd = (
        f"source {OMNETPP_ENV} && "
        f"export INET_ROOT={INET_ROOT} && "
        f"cd {SIM_DIR} && "
        f"opp_run -n $INET_ROOT/src:../src:. "
        f"-l $INET_ROOT/src/INET -l {MATRIXFACTORY_LIB} "
        f"-c {config} -u Cmdenv omnetpp.ini "
        f"'--sim-time-limit={sim_time}' '--**.simTimeLimit={sim_time}' "
        f"'--result-dir={RES_DIR}' "
        f"{extra_args}"
    )
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Error running {config}: {res.stderr}")
        sys.exit(1)

def extract_pars(sca_path):
    pars = {}
    with open(sca_path, "r") as f:
        for line in f:
            if line.startswith("par ") or line.startswith("param "):
                parts = line.strip().split()
                if len(parts) >= 4:
                    key = f"{parts[1]}.{parts[2]}"
                    pars[key] = " ".join(parts[3:])
    return pars

def extract_scalars(sca_path):
    scalars = {}
    with open(sca_path, "r") as f:
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

def required(scalars, key):
    if key not in scalars:
        raise RuntimeError(f"required scalar {key!r} is absent")
    return scalars[key]

def extract_vectors(vec_path):
    """Return {(module, vector_name): [(time, value), ...]}."""
    headers = {}
    vectors = {}
    with open(vec_path, "r", encoding="utf-8") as stream:
        for line in stream:
            parts = line.strip().split()
            if len(parts) >= 4 and parts[0] == "vector":
                headers[parts[1]] = (parts[2], parts[3].strip('"'))
                vectors[headers[parts[1]]] = []
            elif parts and parts[0] in headers:
                # TV or ETV vector columns; time/value are always the last two.
                vectors[headers[parts[0]]].append((float(parts[-2]), float(parts[-1])))
    return vectors

def main():
    print("=================================================================")
    print("  Checklist C8: Execution Rigor & Validation Suite")
    print("=================================================================\n")

    reuse_results = os.environ.get("VERIFY_C8_REUSE") == "1"

    # Clean only this script's dedicated result directory.
    os.makedirs(RES_DIR, exist_ok=True)
    if not reuse_results:
        for f in os.listdir(RES_DIR):
            path = os.path.join(RES_DIR, f)
            if os.path.isfile(path):
                os.remove(path)

    # 1. Run Cell 1 (CSMA, FIFO), Cell 2 (Sched, FIFO), Cell 3 (CSMA, Prio), Cell 5 (CSMA, TAS)
    cells = ["Cell1", "Cell2", "Cell3", "Cell5"]
    if reuse_results:
        print(f"[*] Reusing existing results from {RES_DIR}")
    else:
        for c in cells:
            print(f"[*] Running {c} for 10s (repetition 0)...")
            extra = "'--**.generationEvents:vector(packetBytes).vector-recording=true'"
            if c == "Cell5":
                extra += " '--**.gateState:vector.vector-recording=true'"
            run_simulation(c, sim_time="10s", extra_args=extra)

    # Map files
    sca_files = {}
    for f in os.listdir(RES_DIR):
        if f.endswith(".sca"):
            for c in cells:
                if f.startswith(c + "-"):
                    sca_files[c] = os.path.join(RES_DIR, f)

    # -------------------------------------------------------------------------
    # Test 1: AMR Spatial Placement Independence (Cell 1 CSMA vs Cell 2 Sched)
    # -------------------------------------------------------------------------
    print("\n[+] Verification 1: AMR Spatial Placement Independence (RNG Isolation)")
    pars_c1 = extract_pars(sca_files["Cell1"])
    pars_c2 = extract_pars(sca_files["Cell2"])

    spatial_match = True
    for i in range(10):
        x_key = f"MatrixFactoryNetwork.amr[{i}].mobility.initialX"
        y_key = f"MatrixFactoryNetwork.amr[{i}].mobility.initialY"
        x1, x2 = pars_c1.get(x_key), pars_c2.get(x_key)
        y1, y2 = pars_c1.get(y_key), pars_c2.get(y_key)
        if x1 is None or y1 is None or x2 is None or y2 is None or x1 != x2 or y1 != y2:
            spatial_match = False
            print(f"  [!] Mismatch on AMR {i}: C1=({x1}, {y1}) vs C2=({x2}, {y2})")

    if spatial_match:
        print("  [✓] PASSED: All 10 AMR spatial coordinates are bit-level identical across CSMA and Sched (rng-2 isolated).")
        sample_x0 = pars_c1.get("MatrixFactoryNetwork.amr[0].mobility.initialX")
        sample_y0 = pars_c1.get("MatrixFactoryNetwork.amr[0].mobility.initialY")
        print(f"      Sample AMR[0]: X={sample_x0}, Y={sample_y0}")
    else:
        print("  [✗] FAILED: AMR coordinates diverged.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Test 2: Offered Load Parity (Cell 1 FIFO vs Cell 3 Prio vs Cell 5 TAS)
    # -------------------------------------------------------------------------
    print("\n[+] Verification 2: Offered Load Parity Across Cells 1, 3, and 5 (rng-1 Traffic)")
    sc_c1 = extract_scalars(sca_files["Cell1"])
    sc_c3 = extract_scalars(sca_files["Cell3"])
    sc_c5 = extract_scalars(sca_files["Cell5"])

    # Check generated packets at each source app
    load_parity = True
    sources = [
        ("FMS Orders", "MatrixFactoryNetwork.fms.app[3].source packets:count"),
        ("Station 0 DDS", "MatrixFactoryNetwork.station[0].app[0].source packets:count"),
        ("Station 0 Telemetry", "MatrixFactoryNetwork.station[0].app[1].source packets:count"),
        ("AMR 0 State", "MatrixFactoryNetwork.amr[0].app[0].source packets:count"),
    ]

    for label, metric in sources:
        v1 = required(sc_c1, metric)
        v3 = required(sc_c3, metric)
        v5 = required(sc_c5, metric)
        if not (v1 == v3 == v5 and v1 > 0):
            load_parity = False
            print(f"  [!] Parity violation for {label}: C1={v1}, C3={v3}, C5={v5}")
        else:
            print(f"  [✓] {label:<22}: Exactly {int(v1)} packets generated in all 3 cells (C1=C3=C5).")

    if load_parity:
        print("  [✓] PASSED: Offered load parity verified bit-identical across wired configurations.")
    else:
        print("  [✗] FAILED: Offered load diverged across cells.")
        sys.exit(1)

    vec_files = {}
    for filename in os.listdir(RES_DIR):
        for cell in ("Cell1", "Cell3", "Cell5"):
            if filename.startswith(cell + "-") and filename.endswith(".vec"):
                vec_files[cell] = os.path.join(RES_DIR, filename)
    if set(vec_files) != {"Cell1", "Cell3", "Cell5"}:
        raise RuntimeError(f"missing offered-load vectors: found {sorted(vec_files)}")
    generated = {cell: extract_vectors(path) for cell, path in vec_files.items()}
    source_keys = sorted(key for key in generated["Cell1"]
                         if ".source" in key[0] and key[1].startswith("generationEvents:vector"))
    if not source_keys:
        raise RuntimeError("no source generationEvents:vector series were recorded")
    for key in source_keys:
        reference = [t for t, _ in generated["Cell1"][key]][:1000]
        if not reference:
            raise RuntimeError(f"empty generation vector {key}")
        for cell in ("Cell3", "Cell5"):
            candidate = [t for t, _ in generated[cell].get(key, [])][:1000]
            if candidate != reference:
                raise RuntimeError(f"generation timestamps differ for {key[0]} between Cell1 and {cell}")
    print(f"  [✓] First up to 1,000 generation timestamps match exactly for all {len(source_keys)} sources.")

    # -------------------------------------------------------------------------
    # Test 3: Packet Conservation in DeadlineSink
    # -------------------------------------------------------------------------
    print("\n[+] Verification 3: Strict Packet Conservation in DeadlineSink")
    conservation_pass = True
    sinks = [
        ("FMS State Sink", "MatrixFactoryNetwork.fms.app[0].sink"),
        ("FMS Telemetry Sink", "MatrixFactoryNetwork.fms.app[1].sink"),
        ("FMS DDS Sink", "MatrixFactoryNetwork.fms.app[2].sink"),
    ]

    for label, prefix in sinks:
        n_total = required(sc_c1, f"{prefix} n_received_total")
        n_warmup = required(sc_c1, f"{prefix} n_filtered_warmup")
        n_horizon = required(sc_c1, f"{prefix} n_filtered_horizon")
        n_valid = required(sc_c1, f"{prefix} n_valid_delivered")
        n_ontime_A = required(sc_c1, f"{prefix} n_on_time_nominal_A")
        n_late_A = required(sc_c1, f"{prefix} n_late_nominal_A")

        # Invariant 1: n_total == n_warmup + n_horizon + n_valid
        if n_total != (n_warmup + n_horizon + n_valid):
            conservation_pass = False
            print(f"  [!] Invariant 1 failed on {label}: total={n_total} != warmup({n_warmup}) + horizon({n_horizon}) + valid({n_valid})")

        # Invariant 2: n_valid == n_ontime_A + n_late_A
        if n_valid != (n_ontime_A + n_late_A):
            conservation_pass = False
            print(f"  [!] Invariant 2 failed on {label}: valid={n_valid} != ontime({n_ontime_A}) + late({n_late_A})")

        print(f"  [✓] {label:<20}: total={int(n_total)} = warmup({int(n_warmup)}) + horizon({int(n_horizon)}) + valid({int(n_valid)}); on_time={int(n_ontime_A)}, late={int(n_late_A)}")

    if conservation_pass:
        print("  [✓] PASSED: Strict packet conservation mathematically confirmed.")
    else:
        print("  [✗] FAILED: Conservation invariant broken.")
        sys.exit(1)

    coordinator = "MatrixFactoryNetwork.experimentCoordinator"
    for cls in ("orders", "dds", "state", "telemetry"):
        generated_count = required(sc_c1, f"{coordinator} n_generated_valid_{cls}")
        outcomes = sum(required(sc_c1, f"{coordinator} {name}_{cls}") for name in
                       ("n_delivered_valid", "n_drop_queue", "n_drop_retry", "n_drop_other", "n_late_termination"))
        if generated_count != outcomes:
            raise RuntimeError(f"full conservation failed for {cls}: generated={generated_count}, outcomes={outcomes}")
        print(f"  [✓] {cls:<10}: generated valid {int(generated_count)} = all terminal outcomes {int(outcomes)}")

    # -------------------------------------------------------------------------
    # Test 4: GCL Gate State Vector Inspection in Cell 5 (TAS)
    # -------------------------------------------------------------------------
    print("\n[+] Verification 4: GCL Gate State Timing in Cell 5 (TAS)")
    # Find .vec file for Cell 5
    vec_c5 = None
    for f in os.listdir(RES_DIR):
        if f.startswith("Cell5-") and f.endswith(".vec"):
            vec_c5 = os.path.join(RES_DIR, f)
            break

    if not vec_c5:
        raise RuntimeError("Cell 5 .vec file is absent")
    vectors = extract_vectors(vec_c5)
    expected = {3: (0.0, 100e-6), 2: (100e-6, 300e-6),
                1: (300e-6, 500e-6), 0: (500e-6, 0.0)}
    checked = 0
    for gate, boundaries in expected.items():
        series = [(key, data) for key, data in vectors.items()
                  if f"transmissionGate[{gate}]" in key[0] and key[1] == "gateState:vector"]
        if not series:
            raise RuntimeError(f"gateState:vector absent for traffic class gate {gate}")
        for key, data in series:
            # Vector recording starts after the configured 5 s warm-up. GCL
            # validation is phase-relative, so absolute recording time is irrelevant.
            times = [time for time, _ in data][:20]
            if not times:
                raise RuntimeError(f"gate vector {key} has no runtime transitions")
            phases = [time % 1e-3 for time in times]
            for phase in phases:
                if not any(min(abs(phase - b), abs(phase - b + 1e-3), abs(phase - b - 1e-3)) < 1e-10
                           for b in boundaries):
                    raise RuntimeError(f"unexpected GCL transition phase {phase}s in {key}")
            for boundary in boundaries:
                if not any(min(abs(phase - boundary), abs(phase - boundary + 1e-3), abs(phase - boundary - 1e-3)) < 1e-10
                           for phase in phases):
                    raise RuntimeError(f"missing GCL boundary {boundary}s in {key}")
            checked += 1
    print(f"  [✓] PASSED: {checked} gate vectors transition only at the four configured GCL boundaries.")

    print("\n=================================================================")
    print("  ALL CHECKLIST C8 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
