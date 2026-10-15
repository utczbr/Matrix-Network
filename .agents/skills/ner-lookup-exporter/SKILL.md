---
name: ner-lookup-exporter
description: >-
  Generate, validate, and interpolate empirical network latency and loss lookup tables from discrete-event simulation outputs for asynchronous consumption by Digital Twin Next Event Request (NER) engines. Use when users export simulation scalars or packet traces into tidy CSV/JSON lookup tables, compute replication confidence intervals, evaluate continuous or tick-quantized deadline misses, or perform monotone PCHIP quantile interpolation.
---

# Digital Twin NER Lookup Table Exporter

A workflow for transforming discrete-event network simulation outputs (per-packet traces or scalar/quantile summaries) into validated lookup tables with 1D Wasserstein monotone PCHIP interpolation for deterministic consumption by digital twin Next Event Request (NER) engines.

## When to Use
- Exporting network simulation results into structured CSV and JSON lookup tables for an external digital twin or co-simulation engine
- Computing continuous relative deadline misses alongside discrete tick-grid consumption misses
- Aggregating replication-level statistics with Student-t confidence intervals and zero-miss Wilson score bounds
- Implementing out-of-grid interpolation across traffic load and fleet/node density dimensions without artificial distribution distortion
- Designing deterministic inverse-transform sampling contracts for multi-threaded or multi-agent simulation runtimes

## Steps

### 1. Apply Unbiased Warmup and Common Horizon Filtering
Ensure all deadline thresholds in the lookup table are evaluated over the exact same unbiased set of packets.

- Discard warmup packets generated prior to transient stabilization ($g < t_{\text{warmup}}$).
- Compute the horizon cutoff using the largest lead time in the deadline spectrum ($L_{\max} = \max(D_{\text{spectrum}})$) on the primary tick grid ($T_0$):
  $$c_{\text{horizon}} = \phi + \left\lceil \frac{g - \phi + L_{\max}}{T_0} \right\rceil \cdot T_0$$
- Discard any packet with $c_{\text{horizon}} > t_{\text{sim\_limit}}$. Using $L_{\max}$ across all deadline columns guarantees that every column shares the same packet denominator $n_{\text{total}}$, keeps miss rates strictly monotone with respect to the deadline threshold $D$, and ensures $\text{Late\_Arrival} = \text{miss}_A(D) - p_{\text{loss}} \ge 0$.
- Assert strict packet conservation ($n_{\text{total}} == n_{\text{delivered}} + n_{\text{Drop\_Queue}} + n_{\text{Drop\_Retry}} + n_{\text{Drop\_Other}}$) before computing rates.

### 2. Separate Physical Loss from Continuous and Tick-Quantized Misses
Preserve both binary loss and graded delay information so the consuming twin can apply class-specific late-arrival semantics.

- Record physical drop probability $p_{\text{loss}} = (n_{\text{Drop\_Queue}} + n_{\text{Drop\_Retry}} + n_{\text{Drop\_Other}}) / n_{\text{total}}$ separately from finite delivery delays.
- Evaluate **Definition A** (continuous relative deadline): $\text{miss}_A(D) = 1$ if lost ($a = \infty$) or $(a - g) > D$.
- Evaluate **Definition B** (discrete tick grid): $c = \phi + \lceil(g - \phi + L_c) / T\rceil \cdot T$ with $L_c = D_c$ and non-strict boundary inequality ($a \le c$ is on time; $a > c$ is a miss).
- Support class-specific late semantics:
  - **Watchdog / KILL flows** (control and coordination): Packets arriving after the protocol watchdog TTL ($a > c_{\text{TTL}}$) are aborted and discarded by the application.
  - **Zero-Order Hold / ZOH flows** (periodic state and telemetry): Late packets cause a miss on tick $c$ (reusing the prior snapshot) and take effect on tick $c' = \phi + \lceil(a - \phi) / T\rceil \cdot T$, incurring discrete tick staleness $\Delta_k = \max(0, \lceil(a - \phi) / T\rceil - \lceil(g - \phi + L_c) / T\rceil)$.

### 3. Aggregate at the Replication Level
Treat the independent simulation replication (not the individual packet) as the primary statistical unit to account for temporal burst correlation.

- Compute the mean miss rate across $R$ replications and the 95% Student-t confidence interval half-width:
  $$H = t_{0.975, R-1} \cdot \frac{s}{\sqrt{R}}$$
- When all replications yield zero misses ($\sum k_r = 0$), report the 95% Wilson score upper bound on pooled packets:
  $$p_{\text{upper}} = \frac{3.8416}{n_{\text{pooled}} + 3.8416}$$
- Set `insufficient_tail_samples = true` whenever the pooled delivered sample count is below $10^4$ for p99 or below $10^5$ for p99.9.

### 4. Interpolate Horizontally in Quantile Space via Monotone PCHIP
Export a two-table schema (`lookup_summary` and `lookup_ecdf`) in tidy CSV and mirrored JSON formats.

- Store conditional delivery delay quantiles ($a < \infty$) across a fixed, tail-dense quantile vector (e.g., 25 levels from 0.000 to 1.000, including 0.90, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999, 1.000).
- Never interpolate vertically in CDF probability space (which creates false bimodal mixture distributions between low-delay and high-delay operating points).
- Interpolate horizontally in quantile space (1D Wasserstein geodesic) along continuous dimensions ($N_{\text{AMR}}$, $\lambda_{\text{tel}}$) by fitting `scipy.interpolate.PchipInterpolator(..., extrapolate=False)` independently to each quantile level $q_k$ and to $p_{\text{loss}}$.
- Apply three post-interpolation guards:
  1. Clip all interpolated delays to $\ge 0.0$ and $p_{\text{loss}}$ to $[0.0, 1.0]$.
  2. Enforce non-crossing across quantile levels via cumulative maximum (`np.maximum.accumulate`).
  3. In post-saturation regimes, snap offered load to the nearest grid point; for out-of-grid queries, clamp to the grid boundary and log a warning (never extrapolate).

### 5. Enforce Deterministic Inverse-Transform Sampling in the Twin
Preserve seeded replay determinism in multi-agent or multi-threaded digital twin runtimes.

- Assign each communicating agent or flow an isolated PRNG stream seeded deterministically from `(runSeed, flowId)`. Never share an unsynchronized PRNG across concurrent agent threads.
- For each message sent at $g$:
  1. Draw $u_{\text{loss}}, u_{\text{delay}} \sim U(0, 1)$ from the flow's PRNG.
  2. If $u_{\text{loss}} < p_{\text{loss}}$, treat the message as physically dropped ($a = \infty$).
  3. Otherwise, locate the bracketing quantile levels $q_k \le u_{\text{delay}} \le q_{k+1}$ via binary search and linearly interpolate delay $\tau$, registering arrival $a = g + \tau$ in the NER registry.

## Gotchas
- **Zero lead time ($L_c = 0$) quantization collapse:** Setting $L_c = 0$ pins consumption to $\lceil g / T \rceil \cdot T$, causing a jitter-free 2 ms link on a 10 ms tick grid to suffer an artificial 20% miss rate. Always set $L_c = D_c$ (or explicitly separate $L_c = T$ as an offline sensitivity variant).
- **Filtering horizon on arrival time $a$:** Truncating packets with $a > t_{\text{sim\_limit}}$ selectively drops delayed packets generated near the end of the run, biasing tail percentiles downward. Always filter on the deterministic consumption tick $c_{\text{horizon}} > t_{\text{sim\_limit}}$.
- **Spline overshoot at queuing knees:** Standard cubic or polynomial splines oscillate across steep finite-buffer saturation knees, producing negative delays or crossing quantiles. Always use Monotone PCHIP plus `np.maximum.accumulate`.
