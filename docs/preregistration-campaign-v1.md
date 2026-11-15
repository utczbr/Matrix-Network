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
| **Digest Split & Commit-Freeze Stamp** | Clean-clone tracked digests in `evidence/DIGESTS.sha256`; host/gitignored artifacts (`libmatrixfactory.so`, `libjemalloc.so.2`, `lookup_ecdf.json`) in `evidence/HOST_ARTIFACTS.sha256` | `sha256sum -c evidence/DIGESTS.sha256` passes `100%` on a clean clone; self-lagging tracked `evidence/00_env/commit.txt` removed, and post-tag verification stamps (`date -u`, `git rev-parse HEAD`, `git describe --tags --exact-match HEAD`, empty `git status --porcelain`) for `verify_c8.py`, `verify_spike_s1.py`, `calibrate_80211.py`, and both digest files are written to gitignored `evidence/05_campaign/gates/` **after** tagging `campaign-v1` so `HEAD == campaign-v1` and `git_dirty == False` hold literally at launch |

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
2. **Unconditional empirical mixture-CDF aggregation across all 1,920 cells:** Summary ECDF tables (`lookup_summary.*` and `lookup_ecdf.*` in `analysis/export_lookup.py` / `analysis/verify_g8a.py`) aggregate cross-replication distributions unconditionally via the exact empirical mixture CDF
   $$\bar{F}(t) = \frac{1}{R}\sum_{r=1}^{R} \hat{F}_r(t)$$
   inverted onto the 25 canonical quantile levels for **every cell in the 1,920-key grid** (removing any data-dependent IQR/threshold switching that would introduce analyst freedom or discontinuities across grid neighbors in G8b interpolation). All summary quantiles are checked directly against `DeadlineSink` scalars under the ratified `G8a.6` limits ($\le 0.05$ high-miss, $\le 0.015$ low-miss). Because raw OMNeT++ `.sca.gz` outputs do not depend on exporter aggregation, implementing this mixture-CDF update in `export_lookup.py` proceeds in parallel after Stage P3 launch and before Stage P3 export/G8a sign-off.

---

## 4. Allocator Canary & Free `pilot_extended` Equivalence Protocol

Although all `192/192` pairs (`rep in {0, 1}`), `12/12` `dry_run_opt` vs `pilot_extended` pairs (`N=80, 12 Mbps, 2000us, rep in {0, 1}`), and 3 tie-heavy `60 s` runs (`rep in {3, 14}`) matched bit-for-bit (`tol = 0.0`) under Tier A + Tier B, residual equivalence and allocator sensitivity over full 22-replication dynamics are verified by two complementary mechanisms:

### 4.1 Free Pre-Optimization Equivalence via `pilot_extended` (`269` Runs, Zero Extra CPU)
The banked pre-optimization directory `simulations/results/pilot_extended` (`evidence/04_pilot_extended/manifest.csv`, built on identical `libmatrixfactory.so` `63dd72db...` with glibc `malloc`) holds `269` completed runs (`89` `N=80, 12 Mbps, 2000us` across Cells 1–6 incl. `44` CSMA `rep=0..14` + `run 1598`, plus `180` `N=10, 54 Mbps, {472us, 600us}`). Because the production campaign re-runs those same seeds under Tier A + Tier B:
- **At Stage P3 barrier (`N in {40, 80}`):** Run `verify_equivalence.py --base-dir simulations/results/pilot_extended --opt-dir simulations/results/campaign --base-manifest evidence/04_pilot_extended/manifest.csv --opt-manifest evidence/05_campaign/manifest.csv --allow-intersection --tol 0.0` (checking all `89` overlapping `N=80` runs at zero extra compute cost).
- **At Stage P4 completion (`10,560` runs):** Run the identical command with `--allow-subset --tol 0.0` to verify all `269/269` `pilot_extended` runs (`90 + 90 + 89`) against `simulations/results/campaign/`, reserving `--no-jemalloc` canary CPU strictly for jemalloc-vs-glibc attribution.

### 4.2 `--no-jemalloc` Allocator Canary Protocol (Reference Oracle & Quarantine Rule)
1. **Scope (run before G6/final promotion; Option B recommended minimum, Option A preferred):**
   - **Option A (1–2% stratified campaign canary, ~110–210 runs):** Sample runs across all 5 values of `N`, both PHYs, all 6 cells, and multiple loads including `rep >= 2` from the production schedule.
   - **Option B (`N=80, 12 Mbps, 2000us` CSMA stress canary, 45 runs):** Re-execute all `45` `Cells {1, 3, 5}`, `rep in {0..14}` high-contention CSMA runs (which exercise multi-seed backoff-0 ties and `rep=3` collapse) with `--no-jemalloc`.
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
4. **Canary Failure, Quarantine, Triage & Recovery Rule:**
   - **Reference oracle:** `--no-jemalloc` (standard glibc `malloc`) is the conservative reference oracle; any non-zero (`tol > 0.0`) divergence on identical binary (`63dd72db...`), config (`8414d45c...`), and RNG seeds is treated as a real allocator/memory sensitivity defect, never as noise.
   - **Immediate halt:** `>= 1` mismatching scalar/statistic field or non-zero canary verification exit immediately halts campaign promotion and downstream export.
   - **Quarantine scope:** Quarantine the **entire affected 6-cell `(nAmr, phy, telInterval)` slice** (all cells `1..6` and all `R` replications containing any mismatched run) so paired contrast symmetry across Cells `1–6` cannot mix allocators.
   - **Triage & isolated rerun procedure:** (i) Re-run each mismatched seed twice under both `--no-jemalloc` and pinned `jemalloc` into scratch directories to classify deterministic FP/tie divergence vs non-deterministic UB/corruption (and run an ASan/UBSan test build on an isolated branch/tmp copy if divergence persists, without altering frozen `libmatrixfactory.so`); (ii) execute the quarantined `(nAmr, phy, telInterval)` slice completely under `--no-jemalloc --allow-unpinned-jemalloc` into an isolated recovery directory (`simulations/results/recovery_nojemalloc/`, `evidence/05_recovery_nojemalloc/`) rather than mixing allocators in `simulations/results/campaign/manifest.csv`, and record the explicit recovery decision in `evidence/LEDGER.md` (or fall back globally to `--no-jemalloc` if systemic divergence affects multiple slices).

---

## 5. `rep = 3` CSMA Contention-Collapse Diagnostic Plan

To explain the `rep = 3` CSMA metastable transition observed at `N=80, 12 Mbps, 2000us` (`Cells 1, 3, 5`: `State 50ms` jump from `1.0–4.3%` to `76.1–80.4%`) without touching production manifests or binaries:
- Re-run only `rep = 3` at `N=80, 12 Mbps, 2000us` (`Cells 1, 3, 5`) into a scratch directory `simulations/results/diag_rep3/` with temporary `opp_run` CLI recording flags (`--**.statistic-recording=true --**.vector-recording=true` on MAC backoff/queue depth vectors).
- Inspect collision rate, retry-drop onset timestamp (`1,497` retry drops in `Cell 1`), and queue backlog growth. Keep production `simulations/results/campaign/` cleanly governed by Tier A (`omnetpp.ini`).

---

## 6. Reconciled Compute Budget & Staged P3 (`23 Nov`) Scope Amendment

### 6.1 Central Planning Budget (`~1,050–1,060 CPU-hours` / `~11.0 Wall-Days`)
Using the verified `192`-run Tier A+B dry run (`evidence/05_dry_run_opt/equivalence_report.json`) across the 8 unique grid loads (`sorted(set(TEL_INTERVAL_TO_MBPS.values()))`, $\bar{\lambda} = 80.17\ \text{Mbps}$):
- **Central planning budget (all-inclusive):** **`~1,050–1,060 CPU-hours` (`~11.0 wall-days` @ 4 workers)**. This headline budget combines:
  1. Unmargined 8-load `PCHIP(N) × linear(λ)` base model: **`881.5 CPU-hours`** (`9.18 wall-days` @ 4 workers, mean `300.5 s/run`, `2.285×` vs `2,013.9 CPU-h` baseline; per-`N`: `N=5: 82.1`, `N=10: 87.8`, `N=20: 105.9`, `N=40: 172.8`, `N=80: 432.9 CPU-h`; earlier `959.6 CPU-h` drafts double-counted the `"2ms"` alias of `22.4 Mbps`).
  2. Empirical `N=10, 54 Mbps` `pilot_extended` superlinearity adjustment (`+9.9%` at `600us` / `411.87 vs 374.63 s`; `+13.7%` at `472us` / `517.04 vs 454.73 s` across `180` runs).
  3. `+10%` adaptive top-up reserve (`R <= 44` for borderline precision slices, deferred to Stage P4), plus co-located `--no-jemalloc` canary (`~8–15 CPU-h`) and `rep = 3` vector diagnostic sharing the same 4 cores.
- **Storage & memory footprint:** **`~2.37 GiB` (`~2.55 GB`)** compressed `.sca.gz` for `10,560` runs (`< 3 GiB` with top-ups vs `38 GiB` host free disk); peak single-worker RSS `183.5 MiB` (`< 0.8 GiB` across 4 workers).

### 6.2 Staged P3 (`23 Nov`) Execution, Unresolved-Slice Rule & Clean Stage Snapshots
Because full 10,560-run completion (`~11.0 wall-days` @ 4 workers) extends beyond `23 Nov` from a `14–15 Nov` launch, P3 adopts a **two-stage slice-major schedule** (`order_runs_slice_major`, never reducing `R = 22`):
1. **Stage P3 Priority Run (`--namrs 80,40`):** Execute all `N in {40, 80}` slices (`4,224` runs: `605.7 CPU-h` base model -> **`~6.3–7.0 wall-days`** on 4 workers including mid-load overhead). Launched `14–15 Nov`, Stage P3 finishes **`~21.5–22.5 Nov`**, leaving **`~1.0–1.5 days`** before `23 Nov` for independent Phase 6 P3 integrity auditing (`analysis/audit_campaign.py --stage-namrs 40,80`), `--allow-intersection` check on all `89` `pilot_extended` `N=80` runs, P3 mixture-CDF export, `--no-jemalloc` canary / `rep=3` diagnostics, and G7/G8a analysis.
2. **Stage P3 Unresolved Collapsed-CSMA Policy (`R = 22`):** Stage P3 reports all `N in {40, 80}` cells cleanly at uniform `R = 22`. Any bimodal/collapsed CSMA slice (`N=80, 12 Mbps` where `rep=3` collapse pushes `need_R > 22`) is explicitly **pre-registered to be reported as unresolved / regime-split at Stage P3 (`R = 22`)** rather than delaying P3 with ad-hoc partial top-ups; symmetric `R <= 44` top-ups (preserving uniform `R` across all 6 cells) run only in **Stage P4**.
3. **Clean Stage-Boundary Snapshots (Halted State Only):** When `--namrs 80,40` exits `0` at the Stage P3 barrier (and again when Stage P4 completes all `10,560` runs), take an immutable SHA-256 snapshot of `manifest.csv` and all completed `.sca.gz` files while the launcher is halted (`analysis/audit_campaign.py --snapshot-sha256 evidence/05_campaign/snapshots/p3_outputs.sha256`, plus copied `manifest_p3.csv` and audit JSON in gitignored `evidence/05_campaign/snapshots/`) — **never committing mid-run artifacts into tracked git history** so `git_dirty == False` remains intact for resume into Stage P4 (`~23–27 Nov`, completing `N in {5, 10, 20}` + `R <= 44` top-ups ahead of `7 Dec` P4).

