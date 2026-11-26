# Interim 20h Deliverable — Stage `final`

- **Generated:** 2026-11-26T05:26:26-03:00
- **Git HEAD:** `e0deb9259d58943723faf178c1dcda41f308914c`
- **Canary status:** PASS — Option B `--no-jemalloc` (45 files, 0 mismatches, tol=0.0).

## Pool Coverage
- `core_r3`: 40/40 slices (720/720 `.sca.gz` files)
- `knee_r3`: 48/48 slices (864/864 `.sca.gz` files)
- `supp_maxr`: 80 slices (10560 `.sca.gz` files)

## Audits & Equivalence
- `canary_nojemalloc_equiv.json`: `True`
- `canary_vs_pilot_equiv.json`: `True`
- `core_r3_g8a.json`: `False`
- `core_r3_phase6.json`: `True`
- `equiv_dry_run_opt_vs_campaign.json`: `True`
- `equiv_pilot_vs_campaign.json`: `True`
- `knee_r3_g8a.json`: `False`
- `knee_r3_phase6.json`: `True`
- `p3_g8a.json`: `False`
- `p3_phase6_audit.json`: `True`
- `supp_maxr_g8a.json`: `False`
- `supp_maxr_phase6.json`: `True`

## Collapse Frequency (Cell 1, N=80, 12 Mbps, 2000 us)
- Primary rule (`state_miss_B_50ms >= 0.50`): **1/45** = 2.2% (Clopper-Pearson 95% CI: [0.1%, 11.8%]); normal (<0.10): 41, intermediate [0.10, 0.50): 3.

## Conformance & G8b Summary
- Conformance (`core_r3`, nominal per-class): {'conforms': 681, 'violates': 256, 'unresolved': 23}
- G8b `core_r3` `lo_N_o` (576 interior pts): median W1 = 0.005 ms, p95 W1 = 3.032 ms, median |d_miss_B| = 0.0000
- G8b `core_r3` `lo_lambda_o` (480 interior pts): median W1 = 0.076 ms, p95 W1 = 6.655 ms, median |d_miss_B| = 0.0000
- G8b `knee_r3` `lo_lambda_o` (864 interior pts): median W1 = 0.017 ms, p95 W1 = 2.771 ms, median |d_miss_B| = 0.0000
