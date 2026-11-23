# Campaign schedule and gates

**Revision:** November 23, 2026

All pre-production gates passed in the pinned environment, and the 80-point Stage P3 validation campaign (`6,947` main-campaign runs + 3 isolated verification pilots) has been executed, audited for exact 5-outcome packet conservation, and synthesized in `report/Project Validation/main.pdf`. Expanding the 32 exploratory operating points ($N_{\mathrm{AMR}} \in \{5, 20\}$) to the full 10,560-run $R=22$ floor and executing downstream Digital Twin replay remain the remaining Phase 4 activities.

## Dependency sequence

1. Build the C++ library with OMNeT++ 6.4, INET 4.7, and GCC 12.2.
2. Run Python unit tests and static GCL/parameter checks.
3. Run C8: source timestamp parity, RNG-isolated placement, runtime GCL
   transitions, domain completeness, and full packet conservation.
4. Run ScheduledDcf acceptance at 54 and 12 Mbps, including N=80.
5. Run the miss-rate pilot. The configured floor is R=22; confirmed by
   pilot_run.py at 6.25% relative error (95% CI).
6. Freeze the grid and launch the production campaign.
7. Export lookup artifacts under strict completeness/conservation checks.
8. Compute paired bottleneck-migration contrasts and perform the twin ingestion
   test before declaring P3 complete.

## Locked production grid

| Factor | Levels |
| --- | --- |
| Cell | 1–6 |
| AMRs | 5, 10, 20, 40, 80 |
| Telemetry payload load | 22.4, 45.0, 60.0, 74.7, 85.0, 95.0, 110.0, 149.3 Mbps |
| PHY | 54, 12 Mbps |
| Replications | 22 minimum, seeds 0–21 |

Total at the current floor: 10,560 runs (**`~1,050–1,060 CPU-hours` / `~11.0 wall-days`** central planning budget on 4 workers, combining the `881.5 CPU-hours` / `9.18 wall-days` unmargined 8-load `PCHIP(N) × linear(λ)` model with `N=10` hold-out superlinearity, `+10%` top-up reserve, and co-located canary/diag; `~2.37 GiB` compressed `.sca.gz`). Per [`preregistration-campaign-v1.md`](preregistration-campaign-v1.md), Stage P3 (`--namrs 80,40`, `4,224` runs / `605.7 CPU-h` base / `~6.3–7.0 wall-days`) completes **`~21.5–22.5 Nov`** leaving **`~1.0–1.5 days`** for Phase 6 P3 integrity audit (`audit_campaign.py`), `--allow-intersection` check on `pilot_extended`, mixture-CDF export, canary/diag, and P3 delivery (reporting collapsed CSMA slices as unresolved at `R = 22`), before taking a halted stage snapshot and completing `N ∈ {5, 10, 20}` + any symmetric `R <= 44` top-ups into P4 (`7 Dec`).

## Exit criteria

- No verifier treats a missing scalar as zero.
- First up to 1,000 generation timestamps per source match in paired cells.
- Runtime gate transitions occur only at 0, 100, 300, 500, and 1000 µs cycle
  boundaries.
- For every class and replication, valid generation equals delivered plus all
  drop categories plus late-at-termination.
- Every delivered packet has complete, nonoverlapping domain timestamps whose
  components sum to end-to-end delay.
- Scheduled retry and retry-limit *count* scalars are zero with nonzero traffic;
  the CSMA control shows retry activity.
- The N=80, 12 Mbps scheduled point has no persistent service deficit.
- Every production key has exactly repetitions 0–21 (or the larger pilot-sized
  set), with no duplicates.
- Zero observed misses are accompanied by a Wilson upper endpoint.
- p99 and p99.9 adequacy are reported independently.
- `lookup_replications.csv` yields paired wireless and wired contrasts with
  confidence intervals.

## Deliverables

- `lookup_summary.csv/.json`
- `lookup_ecdf.csv/.json` with 25 quantile levels
- `lookup_replications.csv`
- `bottleneck_migration.csv`
- validation logs from C8, ScheduledDcf, and the statistical pilot

See [`results.md`](results.md) for the current evidence status. Until all gates
above pass, no prior pilot number is a production result.
