# Matrix Factory Twin: Validation Plan

*Prepared 8 November 2026 for the P2 (9 Nov) to P3 (23 Nov) transition. Basis: the `main` snapshot of utczbr/Matrix-Network, its docs and design PDF, and a baseline run in a sandbox that has no OMNeT++ installed.*

## 1. Where things stand

I ran every gate that does not need OMNeT++/INET. The simulator gates have not been run by me; they need your build machine.

| Check (sandbox run) | Result |
| --- | --- |
| `pytest -q` | 52 passed in 1.5 s |
| `analysis/check_gcl.py` | 33/33 checks passed |
| `analysis/check_parameters.py` | passed (`omnetpp.ini` and `parameters.md` agree) |
| Pinned Python deps | install cleanly (numpy 2.1.3, pandas 2.2.3, scipy 1.14.1, matplotlib 3.9.2, pytest 8.3.3) |
| Grid arithmetic from `omnetpp.ini` | 5 N × 8 loads × 2 PHY × 22 reps = 1,760 runs per cell config; × 6 cells = 10,560 |
| Telemetry intervals | all eight map to the documented 22.4 … 149.3 Mbps levels |

Not run yet: build, `verify_c8.py`, `verify_spike_s1.py`, `calibrate_80211.py`, `pilot_run.py`, and the campaign.

### Findings that shape this plan

1. **No campaign launcher exists in the repo.** Nothing orchestrates, resumes, logs or verifies 10,560 runs. Phase 5 specifies one, to be written as `analysis/run_campaign.py`, with the additions from the host audit (finding 7).
2. **No C++ tests.** `DeadlineSink`, `ExperimentCoordinator` and `ScheduledDcf` are covered only by integration verifiers. Phase 2 therefore adds negative controls at two layers: broken inputs to the validators, and broken inputs that should trip the simulator's own fail-fast checks.
3. **The R = 22 evidence is thin.** I reproduced the pilot arithmetic from `results.md` (18 runs needed, 6.25% at R = 22), but it uses z = 1.96 and a standard deviation from only 5 seeds at one operating point (reported as N=10, 54 Mbps, 95 Mbps load). Phase 4 sets a pilot extension and a precision rule.
4. **Python 3.12.3 here versus the locked 3.11.** Decided: production runs and analysis use Python 3.11 (Debian 12 ships 3.11.2). Any other version is a recorded deviation.
5. **Some State misses are structural, not congestion, and the contrast script would misread them.** At N = 80 and 12 Mbps the scheduled superframe is 90 ms, so State cannot meet 50 ms by construction. The 10 s acceptance run measured 44.96% (Definition A) and 39.45% (Definition B) State misses on 7,923 packets with no drops or retries, matching the uniform-wait derivation in `capacity.md`. `bottleneck_migration.py` computes the wireless effect as CSMA minus scheduled, so that penalty lands in `wireless_gain` and `wireless_minus_wired` and can set `dominant_bottleneck` to wired for the wrong reason.
6. **Orders at N = 80 and 12 Mbps is a capacity-limited schedule, not just geometry.** The same acceptance run measured 49.84% (A) and 42.85% (B) Orders misses at 50 ms, and 7.82% and 6.04% at 100 ms (3,991 packets, no drops or retries), against about 20% from the zero-load gap alone. The 400 Orders per second share 39 AP slots per 90 ms superframe, which is 92% utilization, so queueing carries over between superframes. K = 39 is confirmed (Phase 3): a saturated AP completed exactly 39 exchanges per superframe. My earlier K = 38 fit was a model error. I assumed stationary Poisson arrivals, but the sources start with a uniform offset on 0 to 200 ms, which doubles the arrival rate at the start of the run. That transient is in the 10 s acceptance run (warm-up 0) and is gone by about 3 s, so the 10 s Orders figures overstate the steady state. The 60 s campaign, with a 5 s warm-up, is not affected.
7. **The campaign does not fit the workspace machine.** It has 4 cores, 7.4 GiB RAM (2.1 GiB free) and 38 GiB free disk. Reported timings put the full grid at about 300 to 340 hours (13 to 14 days) against a window of about 168 hours, and raw output at about 74 GB against 38 GiB of disk (histogram bins in every `.sca`, plus `.vec` and `.vci` files that are created even with vector recording off). Phase 5 adds a slice-major run order, sharding and output compression.
8. **`results.md` numbers and reported gate runs are claims, not evidence, until logs are attached.** The README itself says the suite must be rerun. One mismatch already exists: `results.md` lists 23,966 transmissions for N=80, 12 Mbps, while the pinned binary reports 23,968. The workspace traced it to the 18 Oct commit that merged contiguous AP slots (reported from git history; confirm), so results.md predates the current code and needs regenerating with the commit hash beside each number (Phase 2).
9. **Expect many all-zero cells.** `decisions.md` §1.9 reports 64 of 72 baseline points with zero misses, which is why Wilson upper bounds and the `none_or_uncongested` class exist. The analysis plan must say up front how these are reported.
10. **The twin harness has no sampler yet.** Checked against the workspace: the tracked Python files match the snapshot, and the function names quoted earlier (`interpolate_ecdf`, `sample_delay`, `miss_rate_from_quantiles`) were from memory. The real names are `interpolate` and `miss_a_from_quantiles` / `miss_b_from_quantiles`, and there is no inverse-transform sampler, which G8a must add. The gitignored `report/` directory is the only difference between workspace and snapshot.
11. **Domain-share data is recorded but not exported.** `DeadlineSink` records three domain-delay statistics per class (wireless, wired switch, wire serialization and propagation), but the lookup exporter reads scalar lines only. Phase 7 item 4 needed an exporter extension that reads the statistic means; rev 5 adds it (the --domain-delay flag writes lookup\_domain\_delay.csv). No re-run is needed, since those lines are in every `.sca`.
12. **Minor drift:** `export_lookup.py` mentions a 51-test suite (it is 52 now, 70 with the rev 3 and rev 4 patches), and document revision dates disagree (Oct 15, Oct 18, Oct 29). Sync after the rerun.

## 2. What counts as validated

| Question | Evidence | Phase |
| --- | --- | --- |
| Does the build reproduce? | Pinned toolchain, hashes, clean rebuild | 0 to 1 |
| Does the code implement the spec? | Unit tests, acceptance verifiers, determinism, negative controls | 1 to 2 |
| Is the model a believable stand-in for the factory network? | Analytic bounds, cross-checks, sensitivity | 3 |
| Is the campaign adequate and complete? | Pilot sizing, run manifest, independent integrity audit, precision map | 4 to 6 |
| Do the conclusions and the twin interface follow from the data? | Paired contrasts, interaction analysis, hold-out interpolation, replay closure | 7 to 8 |

Most repo checks are *verification* (the code does what the spec says). True *validation* (the model resembles the real system) is limited here to analytic cross-checks and published-value comparisons. The final report should say so plainly.

## 3. Recording rules

```
evidence/
  00_env/  01_build/  02_acceptance/  03_crosschecks/  04_pilot/
  05_campaign/ (manifest.csv, logs/)  06_integrity/  07_analysis/  08_twin/
  LEDGER.md
```

`LEDGER.md` gets one row per gate: date (UTC), source hash, `libmatrixfactory.so` hash, command, exit code, log path, verdict, reviewer.

- Capture every log with `tee` and keep the exit code.
- Any change to `src/`, `omnetpp.ini`, the NED file, the GCL or the toolchain invalidates every gate it touches (`results.md` already lists the rerun triggers).
- No number goes into a thesis figure unless it traces to a manifest row and an exporter output from the frozen binary.

## 4. Phases

### Phase 0. Freeze and record the environment

The tarball has no `.git`, so record the commit separately.

```bash
mkdir -p evidence/00_env
sha256sum repo.tar.gz > evidence/00_env/tarball.sha256
git ls-remote https://github.com/utczbr/Matrix-Network refs/heads/main > evidence/00_env/commit.txt
{ date -u; uname -a; lscpu; free -h; df -h .; } > evidence/00_env/host.txt
{ gcc --version | head -1; python --version; opp_run -v; git -C $INET_ROOT rev-parse --short HEAD; } > evidence/00_env/toolchain.txt 2>&1
pip freeze > evidence/00_env/pip_freeze.txt
sha256sum simulations/omnetpp.ini simulations/MatrixFactoryNetwork.ned src/* requirements.txt > evidence/00_env/source.sha256
```

**Pass:** GCC 12.2, OMNeT++ 6.4.0, INET `dfe270b21f`, Python 3.11 (decided; any other version is a recorded deviation).

**Commit-freeze rule.** A gate counts only when run on a committed tree. `git status --porcelain` must print nothing, and `git rev-parse HEAD` plus the `libmatrixfactory.so` hash go in the ledger with every gate. Ignored files (`report/`, `AGENTS.md`, `analysis/local_config.py`) must not influence any result. The local workspace reported HEAD `7e1355ba…` and a library hash beginning `4c2b7843…`; treat these as a candidate freeze until the clean-tree check and the Phase 1 rebuild are logged.

### Phase 1. Build and static gates

```bash
make clean && make -j$(nproc) 2>&1 | tee evidence/01_build/build.log
sha256sum libmatrixfactory.so > evidence/01_build/lib.sha256
pytest -q -ra 2>&1 | tee evidence/01_build/pytest.log
python analysis/check_gcl.py 2>&1 | tee evidence/01_build/check_gcl.log
python analysis/check_parameters.py 2>&1 | tee evidence/01_build/check_parameters.log
python analysis/capacity.py --out /tmp/capacity.md && diff /tmp/capacity.md docs/capacity.md
```

**Record:** warning count, exit codes, test count. **Pass:** clean link; all tests pass (baseline today: 52); 33/33 GCL checks; parameter check passes; `capacity.md` regenerates with no diff, or the diff is explained.

### Phase 2. Simulator acceptance, determinism and negative controls

```bash
python analysis/verify_c8.py 2>&1 | tee evidence/02_acceptance/verify_c8.log
python analysis/verify_spike_s1.py 2>&1 | tee evidence/02_acceptance/verify_spike_s1.log
python analysis/calibrate_80211.py 2>&1 | tee evidence/02_acceptance/calibrate_80211.log
```

**Compare against what `results.md` reports.** A run with a fixed seed and binary is deterministic, so on the same toolchain these should match exactly. Any difference is a finding to explain before moving on (compiler or INET drift, code changed since Oct 18, or nondeterminism).

| Run | Expected value |
| --- | --- |
| Scheduled, N=40, 54 Mbps, 10 s | 12,100 wireless transmissions; 0 scheduled retries; max State delay 20.238 ms |
| Scheduled, N=80, 12 Mbps, 10 s | 850 µs State slots, 560 µs Orders slots, 39 AP slots, 90 ms superframe; 23,966 transmissions in results.md (the pinned binary reports 23,968; reported cause: the 18 Oct commit that merged contiguous AP slots, which lets one more Orders exchange finish; confirm from git history and regenerate results.md before G2); 0 retries or retry-limit drops; max State delay 90.876 ms; 35,628 valid packets conserved |
| CSMA control, N=40, 54 Mbps | 8 retries |
| C8 | 10 AMR coordinates bit-identical CSMA vs scheduled; first ≤1,000 generation timestamps equal for all 28 sources across Cells 1, 2, 3, 5; 13 sinks and 4 coordinator ledgers conserve exactly; 24 TAS gate vectors transition only at GCL boundaries |

**Evidence rule.** A statement that these gates were run is not evidence. Attach each log, its exit code, the HEAD and library hash, and a line-by-line comparison with the table above. Expected values come from independent records (results.md, derivations), never from the binary being tested; a mismatch is explained, not adopted.

**Determinism test (add this).** Run one Point config twice with the same run number and diff the `.sca` files after stripping header lines (date, run id). They must be identical. Then run with a different seed-set: RNG 1 outputs (generation counts, timestamps) must change while RNG 2 placement stays tied to its own stream as the contract says.

**Negative controls.** Work on scratch copies, never the frozen tree. Each mutation must be caught, and you record which gate caught it. The repo's earlier defects (zero-substituted drops, byte sums matched to packet counts, under-provisioned 12 Mbps slots) were all validator weaknesses, so this is the direct test that they stay fixed.

| Layer | Mutation | Expected outcome |
| --- | --- | --- |
| Validator | Delete one scalar from a copied `.sca` | Exporter aborts (missing is fatal, never zero) |
| Validator | Duplicate or remove one repetition | Exporter aborts (duplicate or incomplete key) |
| Validator | Change one coordinator delivered count by 1 | Conservation audit aborts |
| Validator | Change one sink's tick phase | Global phase equality check aborts |
| Validator | Shift one TAS gate offset by 10 µs | `check_gcl.py` or `verify_c8.py` fails |
| Validator | Set the 12 Mbps Orders slot back to 400 µs | `verify_spike_s1.py` shows a service deficit at N=80 |
| Validator | Leave a gap in one key's repetitions (0 to 20, then 22) | Amended exporter rejects it (seeds must run contiguously from 0) |
| Validator | Give one key fewer repetitions than the floor R | Amended exporter rejects it |
| Validator | Give one cell of a six-cell slice more repetitions than the other five | Amended exporter rejects it (all six share the same k) |
| Simulator | Strip a persistent region tag in a scratch build | Sink or coordinator aborts with `cRuntimeError` |
| Simulator | Disable one persistent-tag boundary record | Run aborts with a missing domain boundary |
| Simulator | Make generation timestamps non-monotonic | Run aborts, or `verify_c8.py` timestamp parity fails |
| Simulator | Use invalid superframe or slot geometry | `ScheduledDcf` aborts at initialization |
| Simulator | Force a negative or overlapping domain delay | Sink aborts on reversed timestamps |

The simulator-layer rows exercise the fail-fast checks the C++ modules are said to contain. Until a control triggers them, those checks are a claim.

### Phase 3. Independent model checks (before spending campaign compute)

These use short runs and derive each expectation from parameters, not from simulator output.

| Check | Derivation | Pass |
| --- | --- | --- |
| FIFO wired queue bound | 80 packets × 117.6 µs = 9.408 ms | Max switch-domain delay in Cells 1 and 2 at 149.3 Mbps ≤ bound plus one frame time (about 0.12 ms) |
| TAS admission wait | From the GCL: a class waits at most one 1 ms cycle plus draining its own window | Cell 5 and 6 per-class switch delay respects it when the class is not oversubscribed |
| Scheduled State delay | Superframe plus exchange time | (max State delay − superframe) is between 0 and about 1 ms across every (N, PHY) at light load; the two acceptance points give 0.238 ms and 0.876 ms |
| Structural State misses, N=80, 12 Mbps | Wait uniform on \[0, 90 ms): (90 − 50)/90 = 44.4% (Definition A), (90 − 55)/90 = 38.9% (Definition B) | Measured State miss within about ±3 points of 45% (A) and 39.5% (B) at 50 ms, 0% at 100 ms, zero drops and retries. The 10 s acceptance run gave 44.96% and 39.45% on 7,923 packets. Repeat on 60 s production data in Phase 6 |
| Orders misses, N=80, 12 Mbps (10 s acceptance run) | Zero-load gap: the AP's 39 slots merge into one 21.84 ms window per 90 ms superframe, so the longest wait is 68.16 ms and about 20% of arrivals exceed 50 ms. That is a lower bound: 400 Orders/s into one shared AP queue is 36 of 39 slots per superframe (92% utilization), so queueing carries over | The 10 s run (3,991 packets, no drops or retries, warm-up 0) gave 49.84% (A) and 42.85% (B) at 50 ms, 7.82% and 6.04% at 100 ms; p50 49.9, p90 95.6, p99 130.4, max 152.8 ms. These include the startup transient (next row) and are not steady-state values. Orders is structural at 50 ms |
| Orders queue model, N=80, 12 Mbps (independent check, corrected) | Eighty sources, each with a first arrival uniform on 0 to 200 ms and then exponential 200 ms gaps (as in the ini), into one FIFO queue served by K=39 slots of 0.56 ms in a 21.84 ms block starting 68 ms into each 90 ms superframe, plus a 0.6 ms wired hop. My simulation, 400 runs of 10 s and 150 runs of 60 s | 10 s, warm-up 0, K=39 with the real startup: A at 50 ms 44.9% (5th to 95th percentile 36 to 55%), A at 100 ms 5.8% (0.9 to 15%), p50 46 ms. The measurement sits inside all three (joint probability about 15%). A stationary-Poisson model puts it outside, which is what misled my earlier K=38 reading; K=38 with the startup overshoots (55%, 12%). Startup excess in mean delay: +43 ms in the first 0.5 s, +32 ms to 1 s, +10 ms to 2 s, about 0 from 2 s, so a 5 s warm-up has a wide margin. **Production expectation (60 s, 5 s warm-up, K=39): A at 50 ms 40% (per-run 5th to 95th percentile 37 to 44%), A at 100 ms 1.7% (0.4 to 3.8%), p50 43 ms.** Pass: the 22-rep production means land within 3 points, 1 point and 3 ms of these (proposed, to ratify; the model's own sampling error for a 22-rep mean is about 0.9 points, 0.5 points and 0.6 ms) |
| AP effective slot capacity (direct, executed) | Saturate the AP queue for 10 superframes at N=80, 12 Mbps and count Orders exchanges | **Measured 390 Orders DATA exchanges in 10 superframes on the fixed binary (`63dd72db...`): K = 39.0** (`1,070` total `packetSentToPeer` = `390` `Orders` DATA frames of `664 B` + `680` `802.11 ACK` frames of `14 B` = `268,480 B`, `scheduledDcf_numGrantReleased = 0`). The 10 s acceptance run on the fixed binary gives `3,991` valid `Orders` packets (`0` drops/retries), `49.84%` (A) and `42.85%` (B) at 50 ms, `7.82%` and `6.04%` at 100 ms, `p50 = 49.870 ms`, `p90 = 95.646 ms`, `p99 = 130.411 ms`, `max = 152.786 ms`. Closes the question |
| Near-structural point, N=80, 54 Mbps | Superframe 48 ms, so State waits up to about 48 ms against a 50 ms deadline | Margin under 2 ms: any added switch delay can push State over. Report it as near-structural, not congestion; confirm against the measured max State delay |
| Wireless airtime | `capacity.py` collision-free lower bound | Measured CSMA busy fraction ≥ bound; CSMA retries and access delay grow with N; scheduled retries stay 0 |
| Offered load | Nominal rate × valid window (roughly 5 s to 59.9 s) | Generated counts per class within Poisson or jitter tolerance; aggregate telemetry matches λ |
| 802.11 calibration | Frame-exchange times from `calibrate_80211.py` | Agree with the exchange times used in the slot geometry (C5) |
| DCF collision model (should) | Unsaturated Bianchi-type analytic model, N = 5 to 80 | CSMA retry or collision rate tracks the model's trend |
| Sensitivity (should) | Vary wired buffer (80 to 40 and 160), AMR placement area, add 24 Mbps PHY at three points | Qualitative conclusions do not flip; otherwise note the dependence on locked values |

**Light-load bounds that would have caught the stranded-frame defect (added 10 Nov).** The Phase 5b dry run found a `ScheduledDcf` defect that every earlier gate missed: at N=5 and 12 Mbps a prefetched Orders frame stayed in `inProgressFrames` until a later arrival, giving a median of 31 ms instead of about 4 ms and 28% misses (fixed in commit 153361a by testing `hasFrameToTransmit()`). The acceptance points were all high-load, where a later arrival always rescues the frame. Run the light-load checks at all ten (N, PHY) points, not only the two acceptance points, and compare Orders against this model before looking at anything else:

| PHY | N | AP frames per superframe | Utilization | Model A@50 | Meas A@50 | Model A@100 | Meas A@100 | Model p50 (ms) | Meas p50 (ms) | Model p99 (ms) | Meas p99 (ms) | Meas State max (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | 5 | 1 | 0.15 | 0.00% | **0.00%** | 0.00% | **0.00%** | 4.0 | **3.88** | 11.3 | **11.18** | **6.953** |
| 12 | 10 | 1 | 0.50 | 0.27% | **0.29%** | 0.00% | **0.00%** | 8.8 | **8.66** | 39.8 | **39.95** | **10.984** |
| 12 | 20 | 3 | 0.67 | 0.71% | **0.53%** | 0.00% | **0.00%** | 13.6 | **13.37** | 47.3 | **44.92** | **21.013** |
| 12 | 40 | 10 | 0.84 | 7.76% | **8.28%** | 0.27% | **0.18%** | 25.1 | **25.08** | 80.7 | **77.82** | **42.972** |
| 12 | 80 | 39 | 0.92 | 39.76% | **38.70%** | 1.79% | **1.33%** | 42.6 | **41.79** | 110.2 | **103.02** | **91.014** |
| 54 | 5 | 2 | 0.04 | 0.00% | **0.00%** | 0.00% | **0.00%** | 1.6 | **1.50** | 3.0 | **2.99** | **3.358** |
| 54 | 10 | 2 | 0.13 | 0.00% | **0.00%** | 0.00% | **0.00%** | 2.6 | **2.59** | 5.1 | **5.24** | **5.379** |
| 54 | 20 | 4 | 0.23 | 0.00% | **0.00%** | 0.00% | **0.00%** | 4.3 | **4.23** | 8.6 | **8.57** | **9.392** |
| 54 | 40 | 16 | 0.25 | 0.00% | **0.00%** | 0.00% | **0.00%** | 7.7 | **7.63** | 17.1 | **17.03** | **20.360** |
| 54 | 80 | 78 | 0.25 | 0.00% | **0.00%** | 0.00% | **0.00%** | 10.7 | **10.77** | 32.4 | **32.37** | **48.355** |

Model: stationary Poisson arrivals at 5 Hz per AMR (the 5 s warm-up removes the startup transient), one FIFO AP queue, back-to-back exchanges one DIFS apart inside the merged block, a 0.1 ms wired hop, 12 runs of 60 s per point. At N=5 and 12 Mbps it gives a median of 4.0 ms, matching the fixed binary (3.9 ms) and not the defective one (31 ms), which is independent support for the fix. A point that disagrees with the table is a lead, not a result. Two consequences: at 12 Mbps the scheduled AP misses the 50 ms Orders deadline from N=40 upward on queueing alone, whatever the wired backbone does, so the 1% conformance target cannot be met there; and at 54 Mbps the AP holds about two frames per 400 µs slot, so utilization is half what one frame per slot would give.

#### Schedule construct validity: is the scheduled arm handicapped by its own design? (added 10 Nov)

Three schedule choices could make the scheduled arm look worse than a well-designed schedule, and so distort the bottleneck-migration contrasts at the root. I checked each against the repo and a light-load model (queueing ignored, so treat the numbers as approximate and confirm them with the runs below).

| Choice | Finding | Action / Executed Result (11 Nov) |
| --- | --- | --- |
| Slot sizes at 54 Mbps | Slots are 400 µs against a needed 258 µs for State (64.5% efficient) and 198 µs for Orders (49.5%); at 12 Mbps they are 95.8% and 98.2%. So the schedule is at its physical floor at 12 Mbps but not at 54 Mbps. At N=80 the superframe is 48 ms; slots at the needed size allow 25 ms (`80 × 0.26 ms + 21 × 0.20 ms = 25.0 ms`). A State wait of up to 48 ms leaves 2 ms to the 50 ms deadline, so FIFO queueing of up to 9.4 ms pushes State over by schedule slack alone | **Executed (`Cells 2, 4, 6`, `N ∈ {40, 80}`, `54 Mbps`, `2000us / 527us / 300us`):** State under `locked` (20/48 ms) vs `tight` (13/25 ms): at `N=40`, max State delay at `300us` is `29.557 ms < 50 ms`, `Late_Arrival = 0.00%` in both, and `Cell 2 − Cell 6` is `43.30%` vs `43.27%`. At `N=80`, `tight` eliminates late arrivals (`MaxDelay = 34.565 ms`, `Late_Arrival = 0.00%`, `Cell 2 − Cell 6 = 42.86%` pure `Drop_Queue`), whereas `locked` adds `+3.30%` (B) / `+8.83%` (A) at `300us`. Follow-up `Orders` check (`Cells 2, 6`, `2000us`, 60s, `rep={0,1}`): `0.00%` misses everywhere, and `tight` strictly reduces `Orders` delays (`N=40` `Cell 2`/`6` `p50 = 4.678/5.509 ms`, `p99 = 10.720/11.530 ms` vs `locked` `7.630/8.649 ms`, `17.028/18.088 ms`; `N=80` `tight_25ms` `9.666/10.715 ms`, `tight_29ms` `7.955/8.976 ms`, `p99 = 20.991..22.220 ms` vs `locked` `10.767/11.444 ms`, `32.367/33.035 ms`). Both schedules are reported; dominant `"wired"` classification above the knee does not flip |
| Phase offset (`cyclePhaseOffset` = 0) | The Orders handoff wait varies by 0.9 to 1.03 ms across offsets at N=5 and 10. The offset (60 µs − N × s\_AMR) mod 1000 µs predicts the optimum (810 µs at N=5, 12 Mbps; 560 µs at N=10, 12 Mbps; 0 µs at N=5, 54 Mbps). The State fleet-aggregate wait is invariant only to shifts of one lattice spacing (200 µs, 50 µs) | **Executed (`Cell 6`, `N ∈ {5, 10}`, `12 & 54 Mbps`, 4 reps/offset):** Dense `0..960 us` sweep confirms sawtooth behavior everywhere. `N=5, 12 Mbps`: `Orders_wlan` rises unit-slope from `3.7237 ms` (`0 us`) to `4.5037 ms` (`780 us`), then drops `1.0305 ms` to `3.4732 ms` (`810 us`). `N=10, 12 Mbps`: `10.3254 ms` (`0 us`) to `10.8554 ms` (`530 us`), dropping to `9.8930 ms` (`560 us`). Dense 54 Mbps (`0,30,60,100..900,960 us`): `N=5` and `N=10` rise monotonically from `1.0838 / 2.1517 ms` (`0 us`) to `1.8664 / 2.9435 ms` (`800 us`), then drop across `t=0` wrap-around to `1.0228 / 2.0546 ms` (`900 us`, only `0.061 / 0.097 ms` below `0 us`) |
| Controller tick phase | Definition B misses at D = 1 ms swing 0 to 5% with the tick phase mod 1 ms in TAS cells. Definition A is not a best case: miss\_B ≤ miss\_A for every phase, which the G8a invariants enforce | The campaign already holds 22 phase draws per key, so analyze miss\_B at D ≤ 2 ms against phase mod 1 ms from `lookup_replications.csv`. No extra runs |
| Transport | The classes are protocol-inspired, open-loop UDP. TCP would break offered-load parity (C8), and the telemetry overload (149 Mbps offered on a 100 Mbps link) exists only for non-reactive traffic | Documented as a scope limit in `decisions.md` §4.1 and the report. Call the classes protocol-inspired, not MQTT or DDS |

The phase offset affects only Cell 6, the one cell where both the wired and wireless sides are time-triggered; Cells 2 and 4 have an ungated wired side.

### Phase 4. Statistical pilot and replication sizing

```bash
python analysis/pilot_run.py 2>&1 | tee evidence/04_pilot/pilot_run.log
```

**Record:** all four task outputs (warm-up transient, FIFO knee, Jain sizing, tail-sample matrix). **Pass:** the script exits 0 (it raises if the requirement exceeds 22); transient stabilizes within 5 s; knee identified near 95 Mbps with Cell 5 showing 0 DDS misses; pooled n ≥ 10^4 for p99.

**Sensitivity of the R = 22 claim.** Using the pilot's own numbers (mean 0.181820, sd 0.027193, 5 seeds):

| Quantity | Value |
| --- | --- |
| Reps for 7% relative error, z = 1.96 (as in `pilot_run.py`) | 18 (reproduced) |
| Half-width at R = 22, z = 1.96 | 6.25% (reproduced) |
| Reps for 7%, Student-t with df = 4 | 36 |
| Half-width at R = 22, t with df = 21, same sd | 6.63% |
| 95% interval for the true sd given only 5 seeds | 0.0163 to 0.0781 |
| Half-width at R = 22 if the true sd is at the upper end | 19.1% |

R = 22 still meets 7% at the point estimate, so I am not saying it is wrong. I am saying the evidence cannot yet distinguish a good floor from a lucky one, and the single point sampled is Cell 1 at the knee. Actions:

1. Extend the pilot to at least 15 seeds at four operating points: Cell 1 at the 95 Mbps knee; a priority cell (3 or 4) at mid load; scheduled N=80 at 12 Mbps; CSMA N=80 at 12 Mbps. Use Student-t. The original pilot point never sampled the N=80 or 12 Mbps regimes.
2. Size on the paired contrast, not single-cell rates. The headline claims are paired differences between cells, which can have smaller variance. Compute the sd of paired differences in the pilot.
3. Apply the precision rule below before launch. If the extended pilot shows 22 is not enough, raise the global floor first.
4. Keep Wilson upper bounds for zero-miss points. Relative error is undefined there.

**Precision rule (locked 8 Nov, with one refinement to ratify).** Evaluate it per (cell, class, N, load, PHY) on the Definition B miss rate at the class nominal deadline, and also on the paired contrasts used in Phase 7.

- Non-zero miss rate: the 95% Student-t half-width H must satisfy H ≤ max(0.07 × mean, 0.005). That is 7% relative where the mean is above about 7%, and 0.5 percentage points absolute below it. The version first agreed switched at a mean of 0.05, which makes the requirement looser just below the switch than just above it; the max form has no step.
- Zero misses in every replication: report the Wilson 95% upper bound on pooled packets.
- Top-up: if any cell of an (N, load, PHY) slice fails after Phase 5, run contiguous extra seeds for all six cells of that slice so pairing stays balanced, up to R = 44. A slice still failing at 44 is reported as unresolved.
- Exporter amendment: replace the exact `--expected-reps` equality with a contiguous floor. Every key has seeds 0 to k−1 with k ≥ R, no gaps or duplicates, and all six cells of a slice share the same k. Land it in the frozen commit with new pytest cases and the Phase 2 negative controls.
- Stopping on precision changes the nominal coverage slightly for topped-up slices. Say so in the report.

**Orders at N=80, 12 Mbps is borderline for the precision rule.** The corrected queue model (K=39, production conditions) gives a per-run sd of about 2.1 points at 50 ms and about 1.0 point at 100 ms, so 22 replications give half-widths of about 0.9 and 0.5 points. The 50 ms target (7% of 40% is 2.8 points) is met comfortably. The 100 ms target, max(7% of 1.7%, 0.5 points) = 0.5 points, is met only just. Budget a few top-up runs for the 80-AMR, 12 Mbps slices, and include Orders at this point in the extended pilot's transient check.

### Phase 5. Campaign dry run and execution

**5a. Write the launcher.** Requirements:

- Enumerates the 6 × 1,760 run numbers per config from the simulator itself (`opp_run -q runnumbers -c CellN_Sweep`; copy the library and NED flags from the command in `verify_spike_s1.py`) and confirms 1,760 each.
- Writes results to `simulations/results/campaign` and confirms on the first two runs that filenames match the exporter's `Cell*_Sweep-*.sca` pattern.
- One log per run, plus a manifest row: cell, nAmr, phy, telInterval, rep, run number, host, start time, wall seconds, exit code, max RSS, `.sca` bytes, `.sca` sha256, library sha256.
- Resumable: skip a run only if its `.sca` exists and parses completely.
- Retry rule: rerun the same run number. Never substitute a seed. A run that fails twice stops the campaign, because a deterministic failure is a model bug.
- Refuses to start if `libmatrixfactory.so` is older than `src/` or its hash differs from the frozen one.

**Additions after the host audit (9 Nov).**

- **Slice-major run order.** Finish all six cells and all 22 replications of one (N, load, PHY) slice before starting the next, with the slices nearest the migration boundary first (high load, N = 40 and 80, both PHY rates). Paired contrasts then work on complete slices as they finish, so a partial campaign can still support P3.
- **Sharding by slice.** `--shard i/M` splits the slice list across machines so no slice is split; results merge into one directory.
- **Output protection.** Delete the `.vec` and `.vci` files after each run (the exporter never reads them), and compress each completed `.sca` to `.sca.gz` after recording the sha256 of the uncompressed file in the manifest. The rev 4 exporter reads `.sca.gz` directly. Compression turns about 9.9 MB into about 0.4 MB at N=80 (reported), which keeps the raw evidence intact. Turning bin recording off from the command line is the alternative, but it changes the run configuration, so compare scalars with and without on one run first and record the change. Test any redirection of vector output before relying on it: the index file path may not accept it.
- **Concurrency from memory, not core count.** Set the worker count from the dry run's max RSS (the machine reports 2.1 GiB free), and stop the campaign if free disk falls below a set margin.
- **Completion check.** Mark a run done only after its output parses and the required scalars are present.

**5b. Dry run (96 runs).** Corner grid: N ∈ {5, 80} × PHY ∈ {54, 12} × load ∈ {22.4, 149.3} × 6 cells × 2 reps. Run it through the full export with `--allow-partial-grid`. This tests the launcher, the exporter and the disk and time budget in one pass.

**5c. Benchmark and budget.** Wall-clock ≈ 10,560 × mean run time ÷ concurrent workers. For illustration: 10 min per run on 32 workers is about 55 hours; 30 min per run is about 6.9 days. The heaviest points are N=80 at 149.3 Mbps, so take the mean from the dry run's corners weighted by the real grid, and measure `.sca` size (bin recording is on) to check disk.

**Host audit (workspace machine, reported 9 Nov).** 4 cores (i5-4460), 7.4 GiB RAM, 38 GiB free disk. Timings: four parallel 60 s runs at N=10 and 95 Mbps took 450 s; one 10 s run at N=80, 12 Mbps took 100 s on a single core, about 10 CPU-minutes per 60 s run. Weighted across the grid that is roughly 1,200 to 1,360 CPU-hours, so 300 to 340 hours on 4 cores against about 168 hours between 11 and 18 Nov. Finishing in about 120 hours needs roughly 10 to 11 cores sustained. Raw output is about 74 GB uncompressed against 38 GiB of disk, and under 2.5 GB compressed. Confirm all of this with the dry run, then choose between more workers and a staged campaign (priority slices complete for P3, the rest by P4).

**5d. Freeze and launch.** Tag the repo (for example `campaign-v1`), record hashes, then launch.

**5e. Monitor.** Failure rate, wall-time outliers, free disk, and any run log containing a missing-tag or missing-boundary abort (fatal per the contract).

**Pass:** 10,560 manifest rows with exit code 0 and a parseable `.sca` each.

### Phase 6. Post-campaign data integrity

**6a. Independent completeness audit.** Write a separate script that does not import `export_lookup`. It reads run headers only and must find exactly one `.sca` for each of the 10,560 keys (cell, nAmr, phy, telInterval, repetition 0 to 21).

**6b. Production export with every gate on.**

```bash
python analysis/export_lookup.py --sca-dir simulations/results/campaign --out-dir artifacts/lookup --expected-reps 22 --domain-delay 2>&1 | tee evidence/06_integrity/export.log
```

Do not pass `--allow-partial-grid`. Record the output hashes. With the amended exporter, `--expected-reps 22` is a floor: topped-up slices carry their larger k, and the audit in 6a must expect the same k.

**6c. Independent conservation re-check.** With your own parser, recompute generated = delivered + queue + retry + other + late-termination for all corner points plus a random 5% of runs (about 530). Compare to the exporter's tables exactly. The exporter should not be the only thing guarding itself.

**6d. Cross-cell parity (expected identical; a deviation is a finding).** For the same (N, load, repetition), valid generated counts per class are identical across all six cells and both PHY rates, because traffic is on RNG 1. Wired-only classes (DDS, Telemetry) have zero wireless domain everywhere. Coordinator and sink delivered counts are equal. Domain components sum to end-to-end delay.

**6e. Physical invariants.**

- Scheduled cells: retry and retry-limit counts are 0 everywhere; CSMA retries rise with N.
- p\_loss excludes late termination; late termination counts as a miss.
- Cells 5 and 6: DDS shows zero misses wherever its TC2 window is not oversubscribed (about 4.4% utilization), reported with a Wilson upper bound.
- Cells 1 and 2: DDS misses appear near the FIFO knee and grow past it, reproducing Finding F1.
- Miss rate is non-decreasing in load and in N, tested with paired differences and confidence intervals (allow noise).
- At 12 Mbps, CSMA State and Orders misses are at least those at 54 Mbps.
- Scheduled N=80 at 12 Mbps: State miss rate inside the structural bands (about 45% ± 3 points under Definition A and 39.5% ± 3 under Definition B at 50 ms, 0% at 100 ms, zero drops and retries; the 10 s acceptance run gave 44.96% and 39.45% on 7,923 packets). Recheck Orders at the same point (Phase 3). Tag both as structural.

**Light-load invariants (added 10 Nov).** In scheduled cells, at every point with schedule utilization below 0.5: State max delay is at most the superframe plus the exchange time plus the wired margin; Orders p50 and p99 sit within the Phase 3 model table; and any radio penalty is labelled `unexplained_radio_penalty`, not accepted as a finding. The stranded-frame defect would have failed all three.

**6f. Tail adequacy, as a prediction.** With a valid window of about 55 s and no loss, pooled delivered counts over 22 reps imply `INSUFFICIENT_TAIL_SAMPLES` for p99.9 (needs 10^5) at State N=5 (about 60k) and Orders N=5 and N=10 (about 30k and 60k), and adequacy from N=10 (State) and N=20 (Orders) upward. If the flags disagree materially, suspect the valid window or the accounting. Report p99 and p99.9 flags separately.

**6g. Precision map.** For every (cell, class, N, load, PHY): achieved relative half-width of the miss rate where it is non-zero, and the Wilson upper bound where it is zero. List keys above 7% and mark which of them sit near a migration boundary.

**Pass:** all of 6a to 6e clean, no unexplained deviations, flags and precision map produced.

### Phase 7. Response surfaces and bottleneck migration

**Pre-register before opening production results:** the conformance target (which class, which deadline, what miss rate counts as conforming; I would propose 1% at the class nominal deadline, for you to ratify), the definition of the dominant domain, and the tolerances used in Phase 8. Fixed on 9 Nov: the Phase 8 tolerances (below) and the conformance target and dominance definition (next paragraph).

**Conformance target and dominance (fixed 9 Nov).**

- A cell conforms for class c at its nominal deadline (5 ms for DDS, 50 ms for State and Orders, 100 ms for Telemetry) when the 95% upper confidence bound on its Definition B miss rate is at most 1%: the mean plus its half-width when the mean is above zero, or the Wilson upper bound on pooled packets when it is zero. Report it per class and jointly across all four classes.
- Where the schedule's zero-load wait already reaches the deadline, label the point structural non-conformance, so a cell that cannot conform by geometry is not read as a network failure.
- The Wilson bound treats packets as independent, and clustered misses are not, so it understates uncertainty near zero. Say so wherever it is used.
- Dominant domain, primary: the contrast classification in `bottleneck_migration.py` as patched. Labels: `structural_schedule_wait`; `none_or_uncongested`; `scheduled_radio_penalty` (wireless effect significantly negative); `wireless` (wireless minus wired significantly positive); `wired` (significantly negative); `mixed_or_uncertain` otherwise.
- Dominant domain, secondary: the delay-share crossing, where the mean wireless share of end-to-end delay exceeds the mean switch share with non-overlapping 95% replication intervals. The exporter extension is in rev 5.

```bash
python analysis/bottleneck_migration.py artifacts/lookup/lookup_replications.csv --out artifacts/lookup/bottleneck_migration.csv
python analysis/bottleneck_migration.py artifacts/lookup/lookup_replications.csv --deadline-ms 10 --out artifacts/lookup/bm_D10.csv
```

1. **Surfaces.** Miss rate against (N, load) per cell, class and PHY at the nominal deadline, and miss-versus-deadline curves over 1, 2, 5, 10, 20, 50, 100 ms (the mitigation for the degenerate metric in `decisions.md` §1.9).
2. **Paired contrasts.** Confirm every key has the same number of paired seeds in all six cells (22, or the common k after top-up). Confirm the sign convention (positive means the second architecture lowers the miss rate). The script reports the wireless effect (CSMA to scheduled, averaged over the three backbones), the wired effects (FIFO to TAS, FIFO to priority, priority to TAS, each averaged over the two radio regimes) and `wireless_minus_wired`, each with a Student-t interval. A significantly negative wireless effect is labelled `scheduled_radio_penalty`, and a wired label survives only when the wired gain clearly exceeds the penalty.
3. **Interaction, mapped to the design hypotheses.** Whether wireless contention neutralizes the 802.1Qbv benefit: compare (Cell 1 − Cell 5) under CSMA with (Cell 2 − Cell 6) under scheduled access, paired by seed. Whether Ethernet delay dominates under coordinated access: how (Cell 2 − Cell 6) grows with load. Which combinations need determinism in both domains: the region where only Cell 6 meets the target. Read these with ceiling compression in mind: where a structural miss rate m already applies to the scheduled cells, a wired effect can only turn the remaining 1 − m of packets into new misses. At N=80, 12 Mbps and D=50 ms, (Cell 2 − Cell 6) is then roughly (1 − m) times (Cell 1 − Cell 5) with no change in how well TAS works (approximate; it assumes wired and structural misses are independent). Cross-check at D = 100 ms, where the State structural rate is 0.
4. **Domain share.** Wireless, switch and serialization share of delivered-packet delay against N and load, per cell. Implemented in rev 5: lookup\_domain\_delay.csv holds the per-run sample count and mean for each class and domain, with audits (every sink has every statistic, the count equals n\_domain\_breakdown\_valid, and the domain means sum to the end-to-end mean). Run the parser on a real .sca before relying on it. The migration point is where shares cross; give a bootstrap interval over replications.
5. **Unresolved cells.** Report the fraction whose interval straddles zero. Do not force a dominant domain on them.
6. **Structural and capacity-limited points (implemented in the rev 3 and rev 4 patches).** The wireless effect subtracts scheduled cells from CSMA cells, so a deterministic schedule wait shows up as a negative wireless gain and can make `dominant_bottleneck` read wired. Wired contrasts inside one radio regime cancel it. For each (class, N, PHY, deadline), compute the zero-load wait implied by the schedule geometry: for State, the superframe; for Orders, the longest gap between AP windows (90 ms minus the merged window at N=80, 12 Mbps). If it reaches the deadline, set `structural_tdma_exceeds_deadline = True`, set the two wireless effects to NaN, label the row `structural_schedule_wait`, and keep the wired contrasts. Flag near-structural points whose bound is within 10% of the deadline. Near-structural points also bias the wired contrast: when the wireless wait leaves only a few ms of margin, wired queueing delay pushes the class over the deadline, so (Cell 2 − Cell 6) at N=80, 54 Mbps measures wired queueing plus schedule slack, not wired queueing alone. Treat wired contrasts there as upper bounds until the tight-slot check in Phase 3 is run. The zero-load bound understates delay where the schedule runs near capacity (Orders at N=80, 12 Mbps is at 92%), so the script also reports `schedule_utilization` and labels a significantly negative wireless effect as `scheduled_radio_penalty` while keeping its numbers: that effect is real and wireless-side, not an artifact to exclude. The label replaces a wired label only when wired does not clearly dominate (the lower bound of the FIFO-to-TAS gain exceeds the size of the penalty), so a saturated FIFO port is not hidden behind a small radio penalty. A separate flag column, scheduled\_radio\_penalty\_flag, is always set.
7. **Robustness.** Do the conclusions hold at the nominal deadline and at fixed deadlines? With hundreds of contrasts, report effect sizes with intervals and do not select significant ones after the fact.

**Record:** figures, CSVs, the pre-registration note with its date.

### Phase 8. Lookup tables and twin ingestion

The Java twin is not in this repo, so Phase 8 splits in two. G8a is a standalone harness that runs here and gates P3. G8b needs a twin harness or a Python equivalent and gates the final report.

**G8a (P3, in this repo).** The snapshot has `interpolate` in `export_lookup.py` but no inverse-transform sampler, so the harness first needs a reference sampler written to `SPEC-lookup-ner-integration.md` §2.2 and tested. If `interpolate_ecdf` and `sample_delay` exist in the local workspace, commit them.

**Status 10 Nov.** The reference sampler (`flow_rng`, `sample_delay`, `sample_flow_ner`) and the harness (`verify_g8a`) are on `main`. The rev 6 patch makes the sampler draw one (loss, latency) pair per message, so batch and message-by-message replay agree, and makes the Monte Carlo check family-wise. The harness stops at the first violation; a run over the full table should collect all of them. A 2-replication dry run cannot pass the low-miss check for TAS cells at D of 1 to 2 ms, because the tick phase beats against the 1 ms gate cycle (sd of the mean about 1.2 points at R=2, about 0.4 at R=22 in my toy model); treat a flag there as noise until 22 replications say otherwise.

1. **Schema.** All columns present, no NaN or Inf, CSV and JSON identical, 25 quantile levels, all 1,920 class-condition keys (4 classes × 480 cells), tail flags present. The twin must honour `INSUFFICIENT_TAIL_SAMPLES` rather than trusting those tails silently.
2. **Seeded replay.** The same (runSeed, flowId) gives bit-identical drops, delays, consumption instants and staleness ticks; a different seed gives a different sequence; each flow has its own stream.
3. **Boundary semantics.** Out-of-grid queries clamp with a logged warning and no extrapolation; post-saturation queries (FIFO above 100 Mbps, TAS telemetry above 44.8 Mbps) snap to the nearest grid node.
4. **Grid nodes.** At every simulated node the 25 quantiles and p\_loss reproduce within 1e-12. This is a plumbing check only: PCHIP passes through its nodes, so it cannot show interpolation accuracy.
5. **Invariants, zero violations.** Quantiles non-crossing; miss rate non-increasing in the deadline (A and B); miss\_B ≤ miss\_A at every spectrum deadline; late-arrival component ≥ −1e-12.
6. **Offline estimate against direct measurement.** `miss_a_from_quantiles` and `miss_b_from_quantiles` against the in-simulation scalars. Where the direct miss rate is at least 0.05: mean error ≤ 2.5 points, worst case ≤ 5 points (an acceptance threshold, not a bound: interpolation error can reach the local knot gap, up to 0.10 mid-range). Ratified 9 Nov: where it is below 0.05, agree within 0.5 points on average and 1.5 points worst case (knot spacing there is 2 points on 0.95 to 0.97 and 1 point on 0.97 to 0.99), because a 2.5 point tolerance exceeds nearly every miss in the low-miss cells and would pass anything there.
7. **Monte Carlo.** 100,000 draws per key through the twin's inverse-transform rule match the table's quantile levels within a family-wise 1% DKW bound (each key tested at 1%/1,920, about 0.0080 at 100,000 draws; a per-key 1% level false-fails about 3 keys in 1,920, as measured), and the loss fraction within its binomial interval.

**G8b (before the final report).**

1. **Hold-out interpolation.** Re-export without an interior N (20) and an interior load (74.7 Mbps), interpolate, and compare with the measured held-out cell: error at p50, p95, p99 and in p\_loss. Test just below and just above the FIFO knee, where PCHIP and clamping matter. Proposed tolerance, to ratify: within 10% relative at p50 and p95, and loss inside the replication interval.
2. **Closure.** The twin's Definition B miss rate from the lookup should agree with the simulator's at the same key, within the replication interval. This tests the whole abstraction. Expect the gap to grow near saturation, because the twin draws loss and delay independently per message and discards burst correlation; the test shows how much that matters.
3. **Java hand-off.** Deliver the validated CSV/JSON bundle with a SHA-256 manifest. The twin maintainers run schema, replay and fidelity checks on their side.

**Pass:** G8a before declaring P3 complete (as `schedule.md` states); G8b before the final report.

## 5. Schedule

Backward from the P3 date, with the campaign length set by the Phase 5c benchmark.

| Dates | Work | Gate |
| --- | --- | --- |
| 8 to 9 Nov | Phases 0 to 2 on the OMNeT++ machine | P2 evidence |
| 10 to 11 Nov | Phases 3 and 4, launcher, dry run, benchmark, freeze | G4, G5a |
| 11 to 18 Nov | Campaign execution and monitoring. At 13 to 14 days on the current 4 cores this needs about 2.5 to 3 times the compute or a staged run (priority slices first for P3, the rest by P4) | G5b |
| 19 to 21 Nov | Phase 6 integrity audit | G6 |
| 21 to 23 Nov | Phase 7 preliminary analysis; Phase 8 G8a | P3 |
| 24 Nov to 7 Dec | Phase 8 G8b, top-up reps if needed, final report | P4 |

If the benchmark puts the campaign past 18 Nov, the options are more workers, or cutting scope with a recorded amendment. Do not shorten replications.

## 6. Go / no-go gates

| Gate | Pass criterion | Evidence |
| --- | --- | --- |
| G0 | Environment matches the lock (Python 3.11), or the deviation is recorded; clean committed tree, HEAD and library hash logged | `00_env/` |
| G1 | Clean build; tests, GCL and parameter checks pass | `01_build/` |
| G2 | C8 and ScheduledDcf acceptance reproduce the `results.md` values, with logs attached; determinism holds; every negative control (validator and simulator layers) is caught | `02_acceptance/` |
| G3 | Analytic cross-checks within tolerance, including the structural State and Orders points | `03_crosschecks/` |
| G4 | Extended pilot passes; precision rule and exporter amendment landed in the frozen commit | `04_pilot/` |
| G5a | Dry run clean; compute budget fits the schedule or a staged plan is agreed; grid frozen and tagged | `05_campaign/` |
| G5b | 10,560 manifest rows (plus any top-up), all exit 0 | `manifest.csv` |
| G6 | Independent audit and exporter agree; invariants and structural bands hold; flags and precision map produced | `06_integrity/` |
| G7 | Pre-registration dated before results; structural points tagged; contrasts, interaction, shares and unresolved cells reported | `07_analysis/` |
| G8a | Standalone replay harness passes: schema, seeded replay, clamping, invariants, offline versus direct, Monte Carlo | `08_twin/` |
| G8b | Hold-out interpolation and closure within tolerance; hand-off bundle delivered | `08_twin/` |

## 7. Decisions: settled and open

1. **Settled (11 Nov):** Python 3.11 for production runs and analysis inside an isolated `.venv` (`numpy 2.1.3`, `pandas 2.2.3`, `scipy 1.14.1`, `matplotlib 3.9.2`, `pytest 8.3.3`) built without `--system-site-packages`. The `numexpr`/`bottleneck` workaround has been removed from `export_lookup.py` and `bottleneck_migration.py`, and all 105 tests pass cleanly.
2. **Settled:** the precision rule in Phase 4 (the continuous max form), the top-up protocol, and the exporter contiguous floor.
3. **Settled 9 Nov:** the conformance target, the dominance definition and the Phase 8 tolerances. **Consequence to accept:** at 12 Mbps scheduled Orders misses 7.8% at N=40 and 40% at N=80 at 50 ms on queueing alone, so the 1% target cannot be met there; report those points as capacity-limited, not as network failures.
4. **Open:** compute for the campaign. The 2-corner dry-run projection is 451 s per run, 1,324 CPU-hours, 13.8 days on 4 workers. Measuring all five fleet sizes (`N = 5, 10, 20, 40, 80`) at `2000us` (`118.0, 142.9, 198.9, 417.1, 1152.3 s`) shows convex $O(N^2)$ wireless-medium scaling: interior points `N = 10, 20, 40` run 24% to 39% faster than the 2-corner linear interpolation, lowering the 5-point grid mean across `N` by 14.8% (to about 1,130 CPU-hours, or 11.8 days on 4 workers). Choose extra workers or a staged campaign.
5. **Settled:** P3 requires G8a, G8b follows.
6. **Settled:** capacity-limited points get the `scheduled_radio_penalty` label, a `schedule_utilization` column and a separate flag; rev 7 adds `unexplained_radio_penalty` for penalties at low utilization and a 1 point floor on penalty flags, and corrects utilization at 54 Mbps.
7. **Settled (re-verified 11 Nov on fixed binary `63dd72db...`):** the 23,966 versus 23,968 difference (18 Oct slot-merging commit) and `K = 39` (saturated AP: `390` `Orders` DATA frames + `680` ACKs = `1,070` frames across 10 superframes, `K = 39.0`, `scheduledDcf_numGrantReleased = 0`).
8. **Settled (11 Nov):** applied both `validation_rev6_review_fixes.patch` and `validation_rev7_analysis.patch`.
9. **Settled (11–12 Nov):** launcher hardening in `analysis/run_campaign.py` (including `validation_rev8_launcher.patch`). Per-run RSS uses `os.wait4` via a post-`execve` `python -S` shim (`run_subprocess_wait4`), preventing `RUSAGE_CHILDREN` accumulation and parent `hiwater_rss` inheritance (`max_rss_kb` scales linearly with `N`: `123.0 MB` at `N=5` to `193.4 MB` at `N=80`). Each simulation child runs in its own session (`start_new_session=True`), `SIGINT`/`SIGTERM` triggers process-group termination via `abort_all_runs` + `atexit` (`tests/test_launcher_abort.py`), pinned launches refuse a dirty git tree unless `--allow-dirty` is passed, manifest rows record `git_head`, `git_dirty`, and `config_sha256` (`compute_config_sha256`), and resume requires matching both `library_sha256` and `config_sha256` (`113` unit tests pass).
10. **Open:** execute Phase 4 extended pilot (`>= 15` seeds at the 4 operating points + paired contrasts) and redo a clean Phase 5b dry run + mid-grid slices (`N=20, 40`) on the finalized committed launcher (`63dd72db...`) within the 10 GB testing budget.
11. **Settled (11 Nov):** removed `docs/Validation_Plan.md` from `.gitignore` so `docs/Validation_Plan.md` is tracked in git as the single canonical versioned home.

## 8. Code review (9 to 12 Nov)

| Item | Finding | Status |
| --- | --- | --- |
| `ScheduledDcf` stranded frames | Root cause plausible and independently corroborated across all 10 `(N, PHY)` light-load points: measured `Cell 2` `Orders` medians (`3.88, 8.66, 13.37, 25.08, 41.79 ms` at 12 Mbps; `1.50, 2.59, 4.23, 7.63, 10.77 ms` at 54 Mbps) match the Phase 3 queue model (`4.0, 8.8, 13.6, 25.1, 42.6 ms` and `1.6, 2.6, 4.3, 7.7, 10.7 ms`) | Accepted & Verified |
| Launcher keeps running queued runs after a failure | Demonstrated: 59 of 59 queued tasks ran after a failure | Fixed, rev 6 patch |
| Manifest header race | Test that fails without the lock | Fixed, rev 6 patch |
| Per-sink domain-statistic check was vacuous | Any sink carrying the statistic satisfied it for all | Fixed, rev 6 patch |
| Sampler draws in two blocks | Batch and message-by-message replay differed | Fixed, rev 6 patch |
| Per-key 99% DKW check | Measured: 3 false failures in 1,920 keys; my specification error | Fixed, rev 6 patch |
| Per-run RSS via `RUSAGE_CHILDREN` | Demonstrated: reports a running maximum. Fixed via `os.wait4` inside a post-`execve` `python -S` shim (`run_subprocess_wait4`) | Fixed, rev 10 |
| Surviving child simulations on `SIGINT`/`SIGTERM`, ignored dirty-tree check, resume ignores config edits | Demonstrated surviving children and accepted dirty/modified configs | Fixed, rev 11 (`validation_rev8_launcher.patch` + `config_sha256` manifest/resume check; 113 tests) |
| Environment workaround | Isolated `.venv` created from `requirements.txt` (`numpy 2.1.3`, `pandas 2.2.3`, `scipy 1.14.1`, `matplotlib 3.9.2`, `pytest 8.3.3`); `numexpr`/`bottleneck` workaround removed | Fixed, rev 10 |
| `wired_tas_penalty` | Logic accepted. Tests use zero-variance data; with no true effect and sd 0.03, 15 of 200 points still got a non-neutral label (7.5%), so labels are screening aids | Accepted with caveat |
| Defect as production data would label it | `scheduled_radio_penalty` at 15% utilization, which reads as a finding | Fixed, rev 7 (`unexplained_radio_penalty`) |
| `schedule_utilization` at 54 Mbps | My error: it assumed one frame per slot, but two fit, so it was twice too high | Fixed, rev 7 |
| Commensurate-clock explanation of the G8a flag | Reproduced in a toy model: miss at D = 1 ms swings 0 to 5% with the tick phase mod 1 ms; sd of the mean 1.2 points at R=2, 0.4 at R=22 | Accepted |
| Budget projection | Arithmetic checks (10,560 × 451.4 s = 1,324 CPU-hours). 5-point `N = 5..80` measurement confirms convex $O(N^2)$ scaling (`~1,130 CPU-hours`) | Validated on `N = 5..80` |
| Phase 3 follow-ups (dense 54 Mbps sweep & tight-slot `Orders`) | Dense 54 Mbps sweep shows `0 us` within `0.06–0.10 ms` of the `900 us` wrap-around minimum; tight `260/200 us` slots keep `0.00%` `Orders` misses and strictly improve `Orders` medians/p99 (`4.68 vs 7.63 ms` at `N=40`, `7.96–9.67 vs 10.77 ms` at `N=80`) | Verified (12 Nov) |
| Clean dry run on finalized launcher | Stale pre-`config_sha256` `dry_run` dir had mixed runs; wipe and re-run corners + `N=20, 40` mid-grid slices on committed launcher | Pending Step 5 |
| Quoted figures | Run 176 (`rep=0`) single-run `Orders` quantiles are `p50 = 3.90 ms`, `p95 = 8.80 ms`; the 2-rep mean (`rep=0, 1`, Runs 176 & 177) in `lookup_summary.csv` is `p50 = 3.88 ms`, `p95 = 8.41 ms` | Resolved |
| Pilot rerun identical to six digits | Expected: the pilot cells use CSMA and FIFO, so they do not exercise the fix | Noted |

## 9. Revision log

| Rev | Date | Change |
| --- | --- | --- |
| 1 | 8 Nov 2026 | First version. |
| 2 | 8 Nov 2026 | Folded in the local-workspace review: structural-miss rule with measured values, negative controls at both layers, commit-freeze rule, precision rule with top-up and exporter amendment, G8 split into G8a and G8b. |
| 3 | 8 Nov 2026 | Exporter contiguous-floor check and structural tagging as a patch (`validation_rev2.patch`): 66 tests, mutation checks caught. |
| 4 | 9 Nov 2026 | Second workspace review: Orders measured, host audit, slice-major order, sharding and compression, conformance target and dominance fixed. Patch `validation_rev4_incremental.patch`. |
| 5 | 9 Nov 2026 | Third workspace review: penalty guard fix, domain-delay parser (`--domain-delay`), 23,966 versus 23,968 explained. Patch `validation_rev5_incremental.patch`: 80 tests. |
| 6 | 9 Nov 2026 | Workspace: saturated-AP measurement (K = 39.0), vector trace, startup-process explanation, domain-delay parser verified on real `.sca`, `results.md` hashes, launcher, sampler and G8a harness implemented (87 tests on a clean checkout of `main`). Reported by the workspace. |
| 7 | 9 Nov 2026 | Review of `main`: reproduced the startup-process explanation (K = 39 fits; my K = 38 reading was a model error) and derived production expectations; fixed halt-on-failure, manifest lock, per-sink check, per-message sampler and family-wise DKW. Patch `validation_rev6_review_fixes.patch`: 93 tests, four mutation checks caught. |
| 8 | 10 Nov 2026 | Review of the dry run and the `ScheduledDcf` fix: fix corroborated by an independent model; `RUSAGE_CHILDREN` shown to report a running maximum; phase-beat explanation reproduced; budget arithmetic checked; my 54 Mbps utilization formula corrected; unexplained-penalty label added; grid-wide Orders predictions and light-load invariants added. Patch `validation_rev7_analysis.patch`: 101 tests, four mutation checks caught. |
| 9 | 10 Nov 2026 | Review of the transport and phase-synchronization discussion: schedule construct validity added to Phase 3 (54 Mbps slot slack, phase offset, controller tick phase, transport scope); corrected my earlier claim that wired contrasts stay valid at near-structural points. No code change. |
| 10 | 11 Nov 2026 | Applied `validation_rev7_analysis.patch`; isolated pinned Python 3.11 `.venv` and removed `numexpr`/`bottleneck` workaround; hardened `run_campaign.py` (`os.wait4` per-child RSS shim, manifest `library_sha256` resume check, `git_head`/`git_dirty`, mandatory `--expected-lib-sha256`, `--timeout-sec`; 105 tests pass); un-ignored `docs/Validation_Plan.md`; re-verified `K = 39.0` saturated-AP capacity, all 10 `(N, PHY)` light-load `Orders` & `State` bounds, the 54 Mbps tight-slot (`260/200 us`) vs locked (`400/400 us`) check, and the `Cell 6` `cyclePhaseOffset` sweep on fixed binary `63dd72db...`. |
| 11 | 12 Nov 2026 | Applied `validation_rev8_launcher.patch` (`start_new_session=True`, `abort_all_runs` on `SIGINT`/`SIGTERM`, `--allow-dirty` enforcement) and closed the `config_sha256` resume gap (`113` tests pass); recorded Phase 3 dense `54 Mbps` `cyclePhaseOffset` sweep and tight-slot `Orders` checks (`0.00%` misses, strictly lower tails). |
