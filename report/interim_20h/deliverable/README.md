# Interim 20h Deliverable — Stage `block_A`

- **Generated:** 2026-11-15T19:49:58-03:00
- **Git HEAD:** `a526020091b78aa1a71aa84296801a2035a139b4`
- **Canary status:** pending — Option B (`--no-jemalloc` canary) scheduled for P3.

## Pool Coverage
- `core_r3`: 26/40 slices (468/720 `.sca.gz` files)
- `knee_r3`: 34/48 slices (612/864 `.sca.gz` files)
- `supp_maxr`: 47 slices (1074 `.sca.gz` files)

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
- Primary rule (`state_miss_B_50ms >= 0.50`): **1/15** = 6.7% (Clopper-Pearson 95% CI: [0.2%, 31.9%]); normal (<0.10): 14, intermediate [0.10, 0.50): 0.

## Conformance & G8b Summary
- Conformance (`core_r3`, nominal per-class): {'conforms': 442, 'violates': 168, 'unresolved': 14}
- G8b `core_r3` `lo_N_o` (240 interior pts): median W1 = 0.005 ms, p95 W1 = 0.908 ms, median |d_miss_B| = 0.0000
- G8b `core_r3` `lo_lambda_o` (288 interior pts): median W1 = 0.059 ms, p95 W1 = 6.810 ms, median |d_miss_B| = 0.0001
- G8b `knee_r3` `lo_lambda_o` (576 interior pts): median W1 = 0.014 ms, p95 W1 = 2.757 ms, median |d_miss_B| = 0.0000
