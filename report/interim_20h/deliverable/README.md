# Interim 20h Deliverable — Stage `block_B`

- **Generated:** 2026-11-16T07:15:43-03:00
- **Git HEAD:** `23fa6349abefd677365c1003bc5735062ff433cb`
- **Canary status:** pending — Option B (`--no-jemalloc` canary) scheduled for P3.

## Pool Coverage
- `core_r3`: 40/40 slices (720/720 `.sca.gz` files)
- `knee_r3`: 40/48 slices (720/864 `.sca.gz` files)
- `supp_maxr`: 56 slices (1266 `.sca.gz` files)

## Audits & Equivalence
- `core_r3_g8a.json`: `False`
- `core_r3_phase6.json`: `True`
- `equiv_dry_run_opt_vs_campaign.json`: `recorded`
- `equiv_pilot_vs_campaign.json`: `recorded`
- `knee_r3_g8a.json`: `False`
- `knee_r3_phase6.json`: `True`
- `supp_maxr_g8a.json`: `False`
- `supp_maxr_phase6.json`: `True`

## Collapse Frequency (Cell 1, N=80, 12 Mbps, 2000 us)
- Primary rule (`state_miss_B_50ms >= 0.50`): **1/45** = 2.2% (Clopper-Pearson 95% CI: [0.1%, 11.8%]); normal (<0.10): 41, intermediate [0.10, 0.50): 3.

## Conformance & G8b Summary
- Conformance (`core_r3`, nominal per-class): {'conforms': 681, 'violates': 256, 'unresolved': 23}
- G8b `core_r3` `lo_N_o` (576 interior pts): median W1 = 0.005 ms, p95 W1 = 3.032 ms, median |d_miss_B| = 0.0000
- G8b `core_r3` `lo_lambda_o` (480 interior pts): median W1 = 0.076 ms, p95 W1 = 6.655 ms, median |d_miss_B| = 0.0000
- G8b `knee_r3` `lo_lambda_o` (672 interior pts): median W1 = 0.018 ms, p95 W1 = 3.190 ms, median |d_miss_B| = 0.0000
