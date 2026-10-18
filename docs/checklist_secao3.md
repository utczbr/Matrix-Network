# Section 3 implementation checklist

**Revision:** October 15, 2026

## Implemented

- [x] Six-cell FIFO/Priority/TAS × CSMA/Scheduled topology.
- [x] Four traffic classes with locked payloads, rates, PCP mapping, and
  Definition-A/Definition-B deadline spectrum.
- [x] Exact raw-time tick and ScheduledDcf arithmetic.
- [x] One replication-global phase per tick period.
- [x] Persistent packet identity, source accounting, and explicit AP/switch
  domain boundaries.
- [x] Exhaustive generated-to-terminal ledger, including late termination.
- [x] Direction-specific 12 Mbps scheduled slots serviceable through N=80.
- [x] 25-level conditional-delay quantile contract in C++ and Python.
- [x] Strict Stage-2 exporter with Wilson upper bounds, separate tail flags,
  repetition/full-grid gates, and nonzero physical-drop ingestion.
- [x] Paired-seed bottleneck migration analysis.
- [x] Pinned Python dependency manifest.

## Must pass before P3

- [x] Clean build and link under the pinned GCC 12.2 toolchain.
- [x] Full Python test suite.
- [x] C8 generation-timestamp, placement, runtime-GCL, domain, and conservation
  verification.
- [x] ScheduledDcf acceptance at 54/12 Mbps, especially N=80 at 12 Mbps.
- [x] Primary Definition-B miss-rate pilot; confirm or raise R=22 (confirmed R=22 at 6.25% relative error).
- [ ] Complete 10,560-run campaign with no missing/duplicate keys.
- [ ] Lookup export and paired bottleneck-migration review.
- [ ] Digital-twin ingestion/replay test.

## Invariants checked by automation

- RNG 0 MAC, RNG 1 traffic/global phases, RNG 2 placement.
- Common 5 s warm-up and 100 ms horizon population.
- `generated_valid = delivered + queue + retry + other + late_termination`.
- `p_loss` excludes delivered lateness and late termination.
- TTL comparison is direct (`a > g + TTL`).
- Domain components are explicit, complete, nonnegative, and additive.
- Missing metrics are fatal; count metrics never include byte-sum siblings.
- p99 requires delivered pooled n≥10,000; p99.9 requires n≥100,000.
