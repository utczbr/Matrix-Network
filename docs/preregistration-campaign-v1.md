# Pre-Registration Note — `campaign-v1` (Locked Before Production Results)

**Date:** 2026-11-14 (locked prior to `campaign-v1` tag and production shard execution)  
**Scope:** Freeze evaluation criteria, `G8a.6` aggregation policy, allocator canary verification, diagnostic reruns, reconciled compute budget, and staged P3/P4 delivery prior to opening production results from `simulations/results/campaign/`.

---

## 1. Frozen Production Provenance (`campaign-v1`)

| Artifact | Value / Path | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Toolchain** | Debian 12 (`6.1.0-52-amd64`), GCC `12.2.0`, OMNeT++ `6.4.0`, INET `4.7.0` (`dfe270b21f`), Python `3.11.2` (`.venv`) | `AGENTS.md`, `evidence/00_env/toolchain.txt` |
| **Compiled Library** | `libmatrixfactory.so`: `63dd72db2c651bb680c898e2fc208e1263521253de956ba78fe448112414acc9` (`src/` unmodified) | `--expected-lib-sha256` + manifest & resume check |
| **Deferred C++ Optimization** | Unapplied reference patch archived at [`docs/patches/speedup_bit_identical.patch`](patches/speedup_bit_identical.patch) (`git apply --check` clean) | Not compiled into `campaign-v1` |
| **Allocator (Tier B)** | `/usr/lib/x86_64-linux-gnu/libjemalloc.so.2` (`libjemalloc2` `5.3.0-1`): `9a2fa29d3386480f7eabdfd39e97dc5e5eeaf923cb82f7e268a3adf738ae08c6` | Mandatory `--expected-jemalloc-sha256` on pinned launches; `validate_manifest_consistency()` rejects mixed rows |
| **Config & Topology (Tier A)** | `simulations/omnetpp.ini` (`8414d45c...`) + `simulations/MatrixFactoryNetwork.ned` (`d3287852...`) (`compute_config_sha256()`) | `check_parameters.py` whitelist/no-override guard + manifest `config_sha256` check |

---

## 2. Phase 7 Conformance Target, Caveats, and Dominance Definitions

Pre-registered before opening any `simulations/results/campaign/` output:

1. **Conformance target (`1%` Definition-B UCB at nominal deadline):**
   - Class nominal deadlines ($T_0 = 10\ \text{ms}$, $L_c = D_c$): `DDS` $5\ \text{ms}$, `State` $50\ \text{ms}$, `Orders` $50\ \text{ms}$, `Telemetry` $100\ \text{ms}$.
   - A cell conforms for class $c$ at operating point $(N, \lambda, \text{PHY})$ iff the 95% upper confidence bound on Definition-B miss rate is $\le 0.01$:
     - Non-zero sample mean: $\bar{m} + t_{0.975,\,R-1}\frac{s}{\sqrt{R}} \le 0.01$.
     - Zero observed misses across all $R$ replications: one-sided Wilson 95% upper bound on pooled valid packets $\le 0.01$.
   - Joint 4-class conformance holds only when all four classes satisfy the bound at that operating point.
2. **Wilson & Structural/Capacity Caveats:**
   - Pooled-packet Wilson bounds assume packet independence and therefore **understate uncertainty under bursty/correlated loss regimes**; every table citing Wilson bounds will state this caveat explicitly.
   - **Structural non-conformance (`structural_schedule_wait`):** Points where deterministic schedule geometry alone reaches the deadline ($\text{worst\_case\_wait} \ge D_{\text{nom}}$, notably `State` at $N=80, 12\ \text{Mbps}$ where $T_{\text{super}} = 90\ \text{ms} \ge 50\ \text{ms}$) are reported separately as geometric non-conformance (`wireless_* = NaN`, wired contrasts retained inside each radio regime).
   - **Capacity-limited schedule (`scheduled_radio_penalty`):** Points with valid geometry (`< D_nom`) whose queueing/utilization pushes the scheduled MAC reliably worse than CSMA (`Orders` at $N=80, 12\ \text{Mbps}$, $\rho \approx 0.92$, `need_R` nominal vs bimodal CSMA) carry explicit `scheduled_radio_penalty_flag = True`.
   - **Near-structural upper bound:** At $N=80, 54\ \text{Mbps}$ ($T_{\text{super}} = 48\ \text{ms}$, within $2\ \text{ms}$ of $50\ \text{ms}$ `State` deadline), `Cell 2 - Cell 6` measures wired FIFO delay **plus schedule slack**, and will be explicitly contextualized alongside the verified tight-slot control (`13/25–29 ms`).
3. **Primary Dominant-Domain Rule (`analysis/bottleneck_migration.py`):**
   - Classification of paired replication contrasts ($\text{wireless} = \frac{(C_1-C_2)+(C_3-C_4)+(C_5-C_6)}{3}$, $\text{wired} = \frac{(C_1-C_5)+(C_2-C_6)}{2}$, $\text{difference} = \text{wireless} - \text{wired}$):
     - `none_or_uncongested`: all six cells show $0.0$ misses.
     - `structural_schedule_wait`: deterministic TDMA bound $\ge D_{\text{eval}}$.
     - `wireless`: difference 95% CI strictly $> 0$ (and no overriding radio penalty).
     - `wired` / `wired_tas_penalty`: difference 95% CI strictly $< 0$ (or positive TAS penalty where TAS degrades telemetry above 44.8 Mbps ceiling).
     - `scheduled_radio_penalty` / `unexplained_radio_penalty`: negative wireless effect $\le -0.01$ with CI strictly $< 0$ (unexplained iff utilization $< 0.5$ and non-structural).
     - `mixed_or_uncertain`: 95% CI straddles zero — reported **unresolved**, never coerced to a domain label.
4. **Secondary Dominant-Domain Rule (`lookup_domain_delay.csv`):**
   - Delay-share crossing point where the 95% replication interval of the wireless domain share exceeds that of the wired switch domain without interval overlap.

---

## 3. Closed `G8a.6` Replication Aggregation Policy (Prior to Phase 8 G8a Freeze)

Pilot (`pilot_extended`) and dry-run (`dry_run`) G8a diagnostics established two distinct behaviors without touching raw `.sca` outputs:
- Unimodal slices (`N=10, 54 Mbps`, 15 reps) pass all `verify_g8a` checks (`G8a.6` max $|e| = 0.0297 \le 0.05$).
- In **bimodal 802.11 CSMA collapse** (`N=80, 12 Mbps, 2000us`: 13 normal seeds around `~5 ms` vs `rep=3` collapse around `~777 ms`), averaging per-replication quantile tables (Wasserstein barycenter in `export_lookup.py`) places the summary median near `~60 ms`, disagreeing with the direct scalar miss rate by `0.5518` at $D=20\ \text{ms}$. Additionally, at `R = 2` on `20 ms` superframes, tick phase beats produce up to `0.1163` discretization steps (`Orders N=20, 12 Mbps, D=10ms`).

**Locked pre-G8a policy:**
1. Raw per-run `.sca.gz` and `lookup_replications.csv` retain exact per-replication quantiles and direct `miss_A`/`miss_B` scalars.
2. Before freezing G8a for P3 sign-off, update summary ECDF aggregation / G8a verification so bimodal or high-dispersion cells (where cross-replication quantile spread indicates regime splitting, e.g., IQR of replication medians exceeds half the evaluation step or $N=80, 12\ \text{Mbps}$ CSMA) export and evaluate via the **exact empirical mixture CDF** $\bar{F}(t) = \frac{1}{K}\sum_{r=1}^K \hat{F}_r(t)$ (inverted to the 25 quantile levels, or reported alongside a discrete regime-split indicator) so summary quantiles match direct `DeadlineSink` scalars within the ratified `G8a.6` limits ($\le 0.05$ high-miss, $\le 0.015$ low-miss).

---

## 4. `--no-jemalloc` Allocator Canary Protocol

Although all `192/192` pairs (`rep in {0, 1}`) and 3 tie-heavy `60 s` runs (`rep in {3, 14}`) matched bit-for-bit (`tol = 0.0`) under Tier A + Tier B, residual allocator sensitivity over full 22-replication dynamics will be audited empirically using `--allow-unpinned-jemalloc`:

1. **Scope (choose at least one before G6 freeze; Option B recommended minimum, Option A preferred):**
   - **Option A (1–2% stratified campaign canary, ~110–210 runs):** Sample runs across all 5 values of `N`, both PHYs, all 6 cells, and multiple loads including `rep >= 2` from the production schedule.
   - **Option B (`N=80, 12 Mbps, 2000us` CSMA stress canary, 45 runs):** Re-execute the 45 completed `Cells {1, 3, 5}`, `rep in {0..14}` high-contention CSMA runs (which exercise multi-seed backoff-0 ties and `rep=3` collapse) with `--no-jemalloc`.
2. **Isolation & Execution Command:** Run strictly into a separate output directory (`--out-dir simulations/results/canary_nojemalloc --evidence-dir evidence/05_canary_nojemalloc`) passing `--expected-lib-sha256 63dd72db2c651bb680c898e2fc208e1263521253de956ba78fe448112414acc9 --no-jemalloc --allow-unpinned-jemalloc` (never mixed into `simulations/results/campaign` or `evidence/05_campaign/manifest.csv`, enforced by `validate_manifest_consistency()`).
3. **Pass Criterion:**
   ```bash
   .venv/bin/python analysis/verify_equivalence.py \
     --base-dir simulations/results/campaign \
     --opt-dir simulations/results/canary_nojemalloc \
     --base-manifest evidence/05_campaign/manifest.csv \
     --opt-manifest evidence/05_canary_nojemalloc/manifest.csv \
     --allow-subset --tol 0.0
   ```
   Must exit `0` with `0` mismatches across every checked scalar and `@statistic` field.

---

## 5. `rep = 3` CSMA Contention-Collapse Diagnostic Plan

To explain the `rep = 3` CSMA metastable transition observed at `N=80, 12 Mbps, 2000us` (`Cells 1, 3, 5`: `State 50ms` jump from `1.0–4.3%` to `76.1–80.4%`) without touching production manifests or binaries:
- Re-run only `rep = 3` at `N=80, 12 Mbps, 2000us` (`Cells 1, 3, 5`) into a scratch directory `simulations/results/diag_rep3/` with temporary `opp_run` CLI recording flags (`--**.statistic-recording=true --**.vector-recording=true` on MAC backoff/queue depth vectors).
- Inspect collision rate, retry-drop onset timestamp (`1,497` retry drops in `Cell 1`), and queue backlog growth. Keep production `simulations/results/campaign/` cleanly governed by Tier A (`omnetpp.ini`).

---

## 6. Reconciled Compute Budget & Staged P3 (`23 Nov`) Scope Amendment

### 6.1 Single Reconciled 10,560-Run Budget (`PCHIP(N) × linear(λ)`)
Using the 8 unique grid loads (`sorted(set(TEL_INTERVAL_TO_MBPS.values()))`, $\bar{\lambda} = 80.17\ \text{Mbps}$) on the verified `192`-run Tier A+B dry run (`evidence/05_dry_run_opt/equivalence_report.json`):
- **Core 10,560-run model:** **`881.5 CPU-hours`** (`9.18 wall-days` @ 4 workers, mean `300.5 s/run`, `2.285×` vs `2,013.9 CPU-h` baseline; per-`N`: `N=5: 82.1`, `N=10: 87.8`, `N=20: 105.9`, `N=40: 172.8`, `N=80: 432.9 CPU-h`).
  - *(Note reconciling earlier drafts: an earlier `959.6 CPU-h` / `10.00 wall-days` number stemmed from calling `.values()` on `TEL_INTERVAL_TO_MBPS` in `export_lookup.py`, which contains 9 keys because `"2ms": 22.4` aliases `"2000us": 22.4` and weighted `22.4 Mbps` twice.)*
- **`N=10` hold-out cross-check & superlinearity reserve:** Against the `N=10, 54 Mbps` `pilot_extended` baseline (`180` runs across `600us` and `472us`), `PCHIP(N) × linear(λ)` predicted `374.63 s` vs measured `411.87 s` (**`1.099×`**) at `600us` (`74.7 Mbps`) and `454.73 s` vs measured `517.04 s` (**`1.137×`**) at `472us` (`95.0 Mbps`).
- **Canonical planning budget (with `+10%` top-up reserve for borderline slices up to `R=44`):**
  - Core + 10% top-up reserve: **`969.6 CPU-hours` (`10.10 wall-days` @ 4 workers)**.
  - Conservative upper planning bound (accounting for mild `+10–14%` mid-load superlinearity + `10%` top-ups): **`~1,060 CPU-hours` (`~11.0 wall-days` @ 4 workers)**.
  - Projected compressed `.sca.gz` storage: **`~2.37 GiB` (`~2.55 GB`)** plus `~10%` for top-ups (`< 3 GiB`, vs `38 GiB` host free disk); peak single-worker RSS `183.5 MiB` (`< 0.8 GiB` total across 4 workers).

### 6.2 Staged P3 (`23 Nov`) Execution Amendment
Because full 10,560-run execution (`~9.2–11.0 wall-days` on 4 workers) spans past `23 Nov` if launched `15 Nov`, P3 adopts a **staged slice-major schedule** (`order_runs_slice_major`, never reducing `R = 22`):
1. **Stage P3 Priority Set (completes ahead of `23 Nov`):** Run all high-`N` slices first (`N in {40, 80}` × `8` loads × `2` PHYs × `6` cells × `22` reps = `4,224` runs; model `605.7 CPU-h` = **`~6.3 wall-days`** on 4 workers, plus higher-load `N=20` slices as wall-clock permits). These slices cover the full wireless saturation, FIFO knee, TAS telemetry saturation, structural TDMA bounds, and bottleneck-migration boundary needed for P3 interim results and G8a/G7 preliminary validation.
2. **Stage P4 Completion (`~23–27 Nov`):** Continue uninterrupted (or add `--shard` workers on a second host with matching pinned `libjemalloc` SHA-256) through remaining `N in {5, 10, 20}` slices to complete all `10,560` runs plus any `R <= 44` top-ups ahead of G6/G8b and the `7 Dec` final report.
