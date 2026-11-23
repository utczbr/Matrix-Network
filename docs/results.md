# Validation and Results Status

**Revision:** November 23, 2026 (`libmatrixfactory.so` at campaign commit `8730cbe`; validation report and synchronized tables archived in `report/Project Validation/`)

Implementation responsibilities are mapped in the corresponding `docs/SPEC-*.md` files. Pre-production acceptance suites, the statistical pilot campaign, and the 80-point Stage P3 validation campaign (`6,947` main-campaign runs across `27,788` `(run, class)` series and `3,106,282,724` valid packets with `0` conservation errors, plus 3 isolated mechanism pilots in `report/Project Validation/pilot_{codesign,gcl,bufparity}/`) are complete and recorded below and in [the validation report](file:///home/stuart/Documentos/Learn/NetWork/Matrix/report/Project%20Validation/main.pdf).

Design coverage comprises confirmatory $R=22$ replications across all 48 operating points at $N_{\mathrm{AMR}} \in \{10, 40, 80\}$, exploratory $R \in \{3, 5\}$ replications across the 32 points at $N_{\mathrm{AMR}} \in \{5, 20\}$, and 23 post-hoc Cell 1 collapse seeds; expanding those 32 exploratory points to the full 10,560-run $R=22$ production floor remains future work. Historical pilot numbers prior to October 15, 2026 were superseded because the earlier scalar exporter substituted zero for physical drop counts, the retry verifier matched byte sums to packet counts, and the scheduled 12 Mbps allocation was underprovisioned. The repaired acceptance and pilot results reported below reflect the corrected, verified toolchain and accounting rules.

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
- `ScheduledDcf::handleMessage` and `ScheduledDcf::channelGranted` now check
  `hasFrameToTransmit()` (covering both `pendingQueue` and prefetched
  `inProgressFrames`) so frames prefetched during an active frame sequence are
  never stranded across TDMA cycles when `pendingQueue` empties (fixing an issue
  caught in the Phase 5b Dry Run where $N=5, 12\text{ Mbps}$ `Orders` E2E delay
  dropped from $44.60\text{ ms}$ to $4.13\text{ ms}$).
- `bottleneck_migration.py` computes paired wireless and wired effects with
  confidence intervals, adding `wired_tas_penalty` / `wired_tas_penalty_flag`
  for TAS-throttled wired flows (e.g., high-load `telemetry`) alongside
  `scheduled_radio_penalty`.
- The quantile contract is synchronized at 25 levels.
- The campaign replication floor is 22, confirmed by the repaired
  primary-miss-rate pilot (achieving 6.25% relative error at 95% CI).
- Tier A (`[General]` `packetNameFormat = "pkt"`, 7-key `@statistic` whitelist
  preceding `**.statistic-recording = false`, `**.bin-recording = false`,
  `**.vector-recording = false`, `**.scalar-recording = true`, and
  `**.eth[*].phyLayer.interFrameGapInserter.duration = 0.96us`, guarded by
  `check_no_production_recording_overrides()`) and Tier B
  (`jemalloc 5.3.0-1` `LD_PRELOAD` enforced via `--expected-jemalloc-sha256`
  and `validate_manifest_consistency()` in `analysis/run_campaign.py`) deliver a
  `2.257×` total (`2.372×` mean paired) speedup and `-27.09 MiB` (`-13.77%`)
  paired mean RSS reduction (`172.74 -> 145.65 MiB`; peak `238.56 -> 183.47 MiB`,
  with `+1.06 MiB` mean rise at `N=5, 2000us` and `-54.87 / -73.88 MiB` at
  `N=80`) while keeping `libmatrixfactory.so` (`63dd72db2c65…`) unchanged
  (deferred Tier C archived unapplied at [`docs/patches/speedup_bit_identical.patch`](patches/speedup_bit_identical.patch))
  and all `192/192` dry-run pairs (`simulations/results/dry_run_opt`,
  `evidence/05_dry_run_opt`) plus `12/12` `pilot_extended` overlapping `N=80` runs (`--allow-intersection`) and all 7 exported tables bit-for-bit identical
  (`0` mismatches across `688,320` required scalars, `771,744` optimized scalars,
  and `369,264` statistic fields; clean-clone tracked digests in
  `evidence/DIGESTS.sha256`, binary/host/ignored artifact digests in
  `evidence/HOST_ARTIFACTS.sha256`, and gate log in `evidence/LEDGER.md`).

## Evidence available in this workspace

Static GCL arithmetic and the Python sources can be checked without producing
campaign evidence. The new C++ translation units compile and link against the
pinned OMNeT++ 6.4.0 / INET 4.7.0 installation. One-second Cell 1 and Cell 2
smoke runs completed: all four classes satisfied generated-to-terminal
conservation, every valid delivery had a complete domain breakdown, and Orders
were delivered through the stripped-tag AP path.

The repaired scheduled-access acceptance trio also completed at its full 10 s
horizon (`libmatrixfactory.so` SHA-256 `63dd72db2c65…`). N=40/54 Mbps recorded 12,100 wireless transmissions, zero scheduled
retries, and 20.238 ms maximum State delay (`Orders` p50 7.958 ms, max 17.230 ms, 29,751 valid packets conserved). N=80/12 Mbps resolved to 850 µs
State slots, 560 µs Orders slots, 39 AP slots, and a 90 ms superframe; it
recorded 23,968 wireless transmissions (up from 23,966 after commit `8a66438ed0` merged contiguous AP slots, allowing one additional `Orders` DATA+ACK exchange—4,026 vs. 4,025—to finish before 10 s), zero retries or retry-limit drops,
90.876 ms maximum State delay (44.96% Definition-A and 39.45% Definition-B misses at 50 ms on 7,923 valid State packets; `Orders` p50 49.870 ms, max 152.786 ms, 49.84% Definition-A and 42.85% Definition-B misses at 50 ms, 7.82% and 6.04% at 100 ms on 3,991 valid Orders packets; these Orders figures come from a 10 s run with `warmup-period = 0 s`, so they include the sources' startup transient (`initialProductionOffset = uniform(0s, 200ms)` doubles the arrival rate at the start) and are not steady-state values), and exact conservation of 35,628 valid packets.
The matched N=40/54 Mbps CSMA control recorded 8 retries. These runs are
acceptance and integration evidence only; they are not pilot or production
results.

Checklist C8 also passes at 10 s: all 10 AMR coordinates match bit-for-bit
between CSMA and scheduled cells; the first up to 1,000 generation timestamps
match for all 28 sources across Cells 1, 2, 3, and 5; all 13 sinks (3 FMS and 10 AMR Orders) and all four
coordinator ledgers conserve packets exactly; and 24 TAS gate vectors transition
only at the configured GCL boundaries.

Checklist C9 (pilot suite) also passes: queue length transients stabilize
within 5.0 s (79.13 pkts transient vs 79.28 pkts steady-state); the FIFO
saturation knee is identified at 95.0 Mbps (Cell 1 drops commence at 1,562 pkts
and 959 DDS misses, while Cell 5 TAS isolates DDS with 0 misses); 5 parallel 60 s
seeds at the knee boundary yield mean miss rate 0.181820 and std dev 0.027193,
confirming that R=22 achieves 6.25% relative error at 95% CI (18 runs required
for 7%); and sample sizes satisfy n >= 10^4 for p99 across all configurations.

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