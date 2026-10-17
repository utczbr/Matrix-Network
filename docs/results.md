# Validation and Results Status

**Revision:** October 15, 2026

Implementation responsibilities are mapped in the corresponding `docs/SPEC-*.md` files. This documentation update adds no new empirical evidence.

No production result is currently claimed. Earlier pilot numbers in this file
were invalidated because the scalar exporter substituted zero for all physical
drop counts, the retry verifier matched both packet counts and byte sums, and
the scheduled 12 Mbps allocation was underprovisioned at N=20, 40, and 80.
Those values must not be cited.

## Implemented repairs

- One `ExperimentCoordinator` draws each NER tick phase once per replication.
- Persistent region tags identify every application packet and record explicit
  AP and TSN-switch boundaries.
- The coordinator records valid generations and terminal outcomes by class.
- `DeadlineSink` rejects missing domain timestamps and uses direct watchdog TTL
  comparison (`arrival > generation + TTL`).
- The Stage-2 exporter requires every scalar, audits full conservation, checks
  global phase equality, rejects duplicate/incomplete repetitions, and uses the
  real queue/retry/other drop counters.
- The exporter reports a Wilson upper endpoint for the nominal miss proportion,
  separate p99/p99.9 adequacy flags, and a paired-replication table.
- `bottleneck_migration.py` computes paired wireless and wired effects with
  confidence intervals.
- The quantile contract is synchronized at 25 levels.
- The campaign replication floor is 22, pending confirmation by the repaired
  primary-miss-rate pilot.

## Evidence available in this workspace

Static GCL arithmetic and the Python sources can be checked without producing
campaign evidence. The new C++ translation units compile and link against the
pinned OMNeT++ 6.4.0 / INET 4.7.0 installation. One-second Cell 1 and Cell 2
smoke runs completed: all four classes satisfied generated-to-terminal
conservation, every valid delivery had a complete domain breakdown, and Orders
were delivered through the stripped-tag AP path.

The repaired scheduled-access acceptance trio also completed at its full 10 s
horizon. N=40/54 Mbps recorded 12,100 wireless transmissions, zero scheduled
retries, and 20.238 ms maximum State delay. N=80/12 Mbps resolved to 850 µs
State slots, 560 µs Orders slots, 39 AP slots, and a 90 ms superframe; it
recorded 23,966 wireless transmissions, zero retries or retry-limit drops,
90.876 ms maximum State delay, and exact conservation of 35,628 valid packets.
The matched N=40/54 Mbps CSMA control recorded 8 retries. These runs are
acceptance and integration evidence only; they are not pilot or production
results.

Checklist C8 also passes at 10 s: all 10 AMR coordinates match bit-for-bit
between CSMA and scheduled cells; the first up to 1,000 generation timestamps
match for all 28 sources across Cells 1, 3, and 5; every sink and all four
coordinator ledgers conserve packets exactly; and 24 TAS gate vectors transition
only at the configured GCL boundaries.

## Mandatory rerun gates

The repository is ready for empirical validation only after all of these pass:

1. Build with the pinned GCC 12.2/OMNeT++ 6.4/INET 4.7 environment.
2. Run `pytest -q`, `check_gcl.py`, and `check_parameters.py`.
3. Re-run `verify_c8.py` after any RNG, traffic, accounting, or GCL change; its
   current timestamp, gate, and conservation checks pass.
4. Re-run `verify_spike_s1.py` after any scheduled-MAC, traffic, or PHY change;
   the current nominal, worst-case, and CSMA-control acceptance points pass.
5. Run `pilot_run.py`; increase `repeat` if its primary Definition-B miss-rate
   sizing exceeds 22.
6. Run the 10,560-cell campaign and export with the full-grid and 22-repetition
   gates enabled.
7. Generate paired bottleneck-migration contrasts and inspect cells whose
   confidence interval does not identify a dominant domain.

Only outputs produced after these gates may populate the final thesis figures
or the digital-twin lookup artifacts.
