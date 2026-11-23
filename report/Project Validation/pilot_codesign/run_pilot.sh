#!/usr/bin/env bash
ROOT="/home/stuart/Documentos/Learn/NetWork/Matrix"
PILOT="$ROOT/report/Project Validation/pilot_codesign"
INI="$PILOT/codesign.ini"
source /home/stuart/omnetpp-6.4.0/setenv >/dev/null 2>&1
export INET_ROOT="/home/stuart/omnetpp-6.4.0/samples/inet-4.7.0"
export LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
set -euo pipefail

rm -rf "$PILOT/results_n40" "$PILOT/results_n80"
mkdir -p "$PILOT/results_n40" "$PILOT/results_n80"

cd "$ROOT/simulations"

for rep in 0 1 2; do
    echo "[$(date -Is)] Starting Cell4_N40_K12 rep=$rep" | tee -a "$PILOT/pilot.log"
    nice -n 4 ionice -c 3 opp_run \
        -n "$INET_ROOT/src:$ROOT/src:$ROOT/simulations" \
        -l "$INET_ROOT/src/INET" -l "$ROOT/matrixfactory" \
        -u Cmdenv -c Cell4_N40_K12 -r "$rep" -f "$INI" \
        "--result-dir=$PILOT/results_n40" >"$PILOT/n40_r${rep}.log" 2>&1
    echo "[$(date -Is)] Finished Cell4_N40_K12 rep=$rep" | tee -a "$PILOT/pilot.log"
done

for rep in 0 1 2; do
    echo "[$(date -Is)] Starting Cell4_N80_SplitAP rep=$rep" | tee -a "$PILOT/pilot.log"
    nice -n 4 ionice -c 3 opp_run \
        -n "$INET_ROOT/src:$ROOT/src:$ROOT/simulations" \
        -l "$INET_ROOT/src/INET" -l "$ROOT/matrixfactory" \
        -u Cmdenv -c Cell4_N80_SplitAP -r "$rep" -f "$INI" \
        "--result-dir=$PILOT/results_n80" >"$PILOT/n80_r${rep}.log" 2>&1
    echo "[$(date -Is)] Finished Cell4_N80_SplitAP rep=$rep" | tee -a "$PILOT/pilot.log"
done

PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/analysis" python3 "$PILOT/parse_pilot.py" | tee -a "$PILOT/pilot.log"
echo "[$(date -Is)] ALL PILOT RUNS AND PARSING COMPLETE" | tee -a "$PILOT/pilot.log"
