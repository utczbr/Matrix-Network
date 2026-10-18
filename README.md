# Matrix Factory Twin: Discrete-Event Simulation Study

OMNeT++/INET study of bottleneck migration in hybrid industrial networks. The
factorial design crosses three wired backbones (FIFO, IEEE 802.1Q priority, and
IEEE 802.1Qbv TAS) with two radio regimes (802.11 DCF and conflict-free
scheduled access).

- Institution: Universidade Federal de Santa Catarina (UFSC), INE
- Authors: Breno da Silva Pereira, Gabriel S. Stuart
- Advisor: Prof. Dr. Antônio Augusto Medeiros Fröhlich
- Status: campaign-readiness repairs implemented; the full validation suite and
  production campaign must be rerun before empirical claims are accepted

## Reproducible environment

The locked toolchain is OMNeT++ 6.4.0, INET 4.7.0
(`dfe270b21f`), GCC 12.2, and Python 3.11. Python dependencies are pinned in
[`requirements.txt`](requirements.txt). Do not mix a library built with a
different C++ ABI into a production campaign.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

source "$HOME/omnetpp-6.4.0/setenv"
export INET_ROOT="$HOME/omnetpp-6.4.0/samples/inet-4.7.0"
make -j"$(nproc)"

pytest -q
python analysis/check_gcl.py
python analysis/check_parameters.py
python analysis/verify_c8.py
python analysis/verify_spike_s1.py
python analysis/pilot_run.py
```

## Experiment contract

- RNG 0: MAC/protocol behavior.
- RNG 1: application traffic and the three replication-global NER phases.
- RNG 2: AMR placement.
- The common valid-generation set uses warm-up 5 s and the 100 ms horizon.
- Every valid generated packet has exactly one terminal outcome: delivered,
  queue drop, retry drop, other terminal drop, or late at termination.
- `p_loss` includes physical drops only; termination and late delivery count as
  deadline misses.
- Domain timing uses persistent packet-region tags at the AP boundary and TSN
  switch queue. Missing instrumentation invalidates the run.
- The NER table uses 25 fixed conditional-delay quantiles and separate p99 and
  p99.9 adequacy flags.

The locked sweep has 6 cells × 5 fleet sizes × 8 telemetry loads × 2 PHY rates
× 22 replications = 10,560 runs. Scheduled 12 Mbps cells use direction-specific
slots (850 µs State, 560 µs Orders) and a 90 ms N=80 cycle so the stress
point is serviceable without exceeding the minimum State interarrival.

## Repository map

```text
analysis/   metrics, validation, exporter, paired bottleneck contrasts
docs/       decisions, parameter catalog, specifications, campaign status
simulations/ OMNeT++ network and six-cell configuration
src/        ScheduledDcf, DeadlineSink, coordinator, persistent packet tag
tests/      deterministic metric/export/contrast tests
```

The production exporter writes `lookup_summary`, `lookup_ecdf`, and
`lookup_replications`. The last table feeds paired-seed bottleneck migration
analysis:

```bash
python analysis/export_lookup.py --sca-dir simulations/results/campaign \
  --out-dir artifacts/lookup --expected-reps 22
python analysis/bottleneck_migration.py artifacts/lookup/lookup_replications.csv \
  --out artifacts/lookup/bottleneck_migration.csv
```

See [`docs/results.md`](docs/results.md) for the evidence status and rerun gates,
and [`docs/decisions.md`](docs/decisions.md) for the mathematical contract.
