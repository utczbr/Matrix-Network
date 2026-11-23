#!/usr/bin/env bash
ROOT="/home/stuart/Documentos/Learn/NetWork/Matrix"
PILOT="$ROOT/report/Project Validation/pilot_gcl"
INI="$PILOT/gcl_pilot.ini"
source /home/stuart/omnetpp-6.4.0/setenv >/dev/null 2>&1
export INET_ROOT="/home/stuart/omnetpp-6.4.0/samples/inet-4.7.0"
export LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
set -euo pipefail

rm -rf "$PILOT/results" "$PILOT/logs" "$PILOT/pilot.log"
mkdir -p "$PILOT/results" "$PILOT/logs"

cd "$ROOT/simulations"

for run_id in $(seq 0 11); do
    echo "[$(date -Is)] Starting Cell6_GCL_Rebal run_id=$run_id" | tee -a "$PILOT/pilot.log"
    nice -n 6 ionice -c 3 opp_run \
        -n "$INET_ROOT/src:$ROOT/src:$ROOT/simulations" \
        -l "$INET_ROOT/src/INET" -l "$ROOT/matrixfactory" \
        -u Cmdenv -c Cell6_GCL_Rebal -r "$run_id" -f "$INI" \
        "--result-dir=$PILOT/results" >"$PILOT/logs/run_${run_id}.log" 2>&1
    echo "[$(date -Is)] Finished Cell6_GCL_Rebal run_id=$run_id" | tee -a "$PILOT/pilot.log"
done

PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/analysis" "$ROOT/.venv/bin/python" "$PILOT/parse_gcl_pilot.py" | tee -a "$PILOT/pilot.log"
echo "[$(date -Is)] ALL GCL PILOT RUNS AND PARSING COMPLETE" | tee -a "$PILOT/pilot.log"

