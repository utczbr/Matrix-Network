#!/usr/bin/env bash
ROOT="/home/stuart/Documentos/Learn/NetWork/Matrix"
PILOT="$ROOT/report/Project Validation/pilot_bufparity"
INI="$PILOT/bufparity.ini"
source /home/stuart/omnetpp-6.4.0/setenv >/dev/null 2>&1
export INET_ROOT="/home/stuart/omnetpp-6.4.0/samples/inet-4.7.0"
export LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
set -euo pipefail

rm -rf "$PILOT/results" "$PILOT/logs" "$PILOT/dry_check" "$PILOT/pilot.log"
mkdir -p "$PILOT/results" "$PILOT/logs" "$PILOT/dry_check"

cd "$ROOT/simulations"

# Quick 10 ms dry verification of TC0=80 packetCapacity override
opp_run \
    -n "$INET_ROOT/src:$ROOT/src:$ROOT/simulations" \
    -l "$INET_ROOT/src/INET" -l "$ROOT/matrixfactory" \
    -u Cmdenv -c Cell3_BufParity -r 0 -f "$INI" \
    --sim-time-limit=10ms --warmup-period=0s \
    "--result-dir=$PILOT/dry_check" >"$PILOT/logs/dry.log" 2>&1

grep -q 'config \*.tsnSwitch\.eth\[0\]\.macLayer\.queue\.queue\[0\]\.packetCapacity 80' "$PILOT/dry_check"/*.sca
echo "[$(date -Is)] 10ms dry check verified TC0 packetCapacity=80" | tee -a "$PILOT/pilot.log"
rm -rf "$PILOT/dry_check"

run_one() {
    local run_id="$1"
    echo "[$(date -Is)] Starting Cell3_BufParity run_id=$run_id" >> "$PILOT/pilot.log"
    opp_run \
        -n "$INET_ROOT/src:$ROOT/src:$ROOT/simulations" \
        -l "$INET_ROOT/src/INET" -l "$ROOT/matrixfactory" \
        -u Cmdenv -c Cell3_BufParity -r "$run_id" -f "$INI" \
        "--result-dir=$PILOT/results" >"$PILOT/logs/run_${run_id}.log" 2>&1
    echo "[$(date -Is)] Finished Cell3_BufParity run_id=$run_id" >> "$PILOT/pilot.log"
}
export -f run_one
export ROOT PILOT INI

seq 0 8 | xargs -n 1 -P 4 bash -c 'run_one "$@"' _

PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/analysis" "$ROOT/.venv/bin/python" "$PILOT/parse_bufparity.py" | tee -a "$PILOT/pilot.log"
echo "[$(date -Is)] ALL BUFPARITY PILOT RUNS AND PARSING COMPLETE" | tee -a "$PILOT/pilot.log"

