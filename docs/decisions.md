# Matrix Factory Twin: Architectural Decisions & Questions Log

**Revision:** Oct 13, 2026 (supersedes the earlier version of this file).

**Status vocabulary**
* **Decision**: adopted in the model, awaiting experimental test.
* **Proposed**: recommended in the Oct 13 review, awaiting team confirmation.
* **Open**: cannot be closed with the information available today (see `checklist_secao3.md`).
* **Verified (analytic)**: recomputed independently on Oct 13, 2026. INET confirmation is still required where noted.

This document records key modeling decisions, mathematical definitions, architectural rationales, and the formal questions submitted to course supervisors and digital twin maintainers.

## Changelog (Oct 13 revision)
1. §1.3: the effect of `L_c = D_c` is stated precisely (slack is uniform in `[D, D+T)`; `delay > D` is necessary, not sufficient). The alternative `L_c = T - D_c` is removed (only valid for `D_c <= T`).
2. §1.4: the `L = 0` formula is corrected to `E[min(delay, T)] / T`.
3. §1.5: loss attribution gains a residual `Drop_Other` bin and a conservation check; undelivered packets at the horizon are classified.
4. §1.6: statistical unit is the replication. Wilson is demoted to a zero-miss upper bound. Sample-size table and percentile reporting rule added.
5. §1.7 and §1.9 (new): primary metric is reported as a miss-vs-deadline curve. Analytic finding F1 (the metric is almost degenerate with placeholder parameters) is recorded.
6. §2: Q5 split into Q5 (scale) and Q6 (real VDA 5050 sizes and rates). New Q7 (DDS flow matrix) and Q8 (grid extension and deadline sensitivity). Per-question "closed on our side / still missing" notes added.
7. §3: new decision rows (open-loop UDP, error-free channel by scope, replication as unit, miss-vs-D reporting, internal lookup schema) and two open rows (telemetry process, grid design).
8. §4 (new): egress-port interference matrix. §5 (new): internal lookup-table schema. §6 (new): analytic checks. §7 (new): sync items for the other docs.

---

## 1. Primary Evaluation Metric: Deadline Miss Formulations

### 1.1 Notation
* $g$: packet generation/creation timestamp at the producer application.
* $a$: packet arrival timestamp at the consumer application ($a = \infty$ if the packet is dropped or lost).
* $T$: digital twin discrete-event simulation tick period (nominal: $10\ \text{ms}$).
* $D_c$: application deadline for traffic class $c$.
* $L_c$: processing lead time for traffic class $c$.
* $\text{delay} = a - g$ (with $\text{delay} = \infty$ for lost packets).

### 1.2 Definition A: Relative Deadline (continuous-time baseline)
$$\text{Miss}_A = \begin{cases} 1 & \text{if packet is lost or } (a - g) > D_c \\ 0 & \text{otherwise} \end{cases}$$

* Depends only on packet lifetime. Independent of the tick grid, so it does not depend on the answer to Q1.
* Can be reconstructed from delay histograms. Reported for every class, cell and grid point as the baseline.

### 1.3 Definition B: Tick Grid Consumption Instant (digital twin event consumption)
The Next Event Request (NER) engine advances in ticks of period $T$. An event generated at $g$ with lead time $L_c$ is consumed at
$$c = \left\lceil \frac{g + L_c}{T} \right\rceil \times T, \qquad \text{Miss}_B = \begin{cases} 1 & \text{if packet is lost or } a > c \\ 0 & \text{otherwise} \end{cases}$$

**Adopted choice: $L_c = D_c$** (status: Decision, pending Q1 confirmation).

Verified properties of this choice (Oct 13):
* The time available between generation and consumption, $s = c - g$, lies in $[D_c, D_c + T)$ and is uniform on that interval when $g$ is uniform within a tick.
* Therefore $\text{delay} > D_c$ is a **necessary but not sufficient** condition for a miss. A packet with $D_c < \text{delay} < s$ is still consumed on time.
* Consequences: $\text{Miss}_B \le \text{Miss}_A$ for every packet, and
$$P(\text{Miss}_B) = \frac{1}{T}\int_0^T P(\text{delay} > D_c + x)\,dx \qquad (\text{lost packets: } \text{delay} = \infty).$$
  For a deterministic delay this gives $\min\big(\max(\text{delay} - D_c, 0),\, T\big)/T$.
* Definition B with $L_c = D_c$ is therefore a smoothed, less strict version of A. Both are reported (§1.7).

**Removed alternative: $L_c = T - D_c$.** It only makes sense for $D_c \le T$. For the 50 ms classes it yields $L_c = -40\ \text{ms}$. For DDS ($D_c = 5\ \text{ms}$, $T = 10\ \text{ms}$) it coincides with $L_c = D_c$.

### 1.4 Pitfall of Definition B with $L = 0$
If $L_c = 0$ and $g$ is uniform within a tick, a packet generated at phase $u$ must arrive within the remaining $T - u$:
$$P(\text{miss}) = \frac{1}{T}\int_0^T P(\text{delay} > x)\,dx = \frac{\mathbb{E}[\min(\text{delay}, T)]}{T}$$
which equals $\mathbb{E}[\text{delay}]/T$ only when delays are below $T$.

* **Consequence:** a constant $2\ \text{ms}$ delay produces a $20\%$ miss rate in every cell, purely from tick-phase quantization. The metric collapses to mean delay over $T$ and hides jitter improvements from TSN and scheduled access.
* **Adopted solution:** class-dependent $L_c = D_c$, plus Definition A reported as the continuous baseline.

### 1.5 Counting rules and boundary conditions
1. **Warmup filter:** discard packets with $g < t_{\text{warmup}}$.
2. **Horizon filter:** discard packets with $c > t_{\text{sim-limit}}$. The filter uses $c$, which depends only on $g$, so it does not bias the sample. Never filter on $a$. With $L = D = 50\ \text{ms}$ and $T = 10\ \text{ms}$ up to 60 ms of tail is excluded.
3. **Causal attribution** (mutually exclusive and exhaustive):
   * `Drop_Queue`: buffer overflow at switch, AP or node (`packetDropQueueOverflow`).
   * `Drop_Retry`: 802.11 retry limit reached (`packetDropRetryLimitReached`).
   * `Drop_Other` (**new**): any other INET drop reason (for example incorrectly received at PHY). Expected to be empty under the error-free channel (§3).
   * `Late_Arrival`: delivered with $a > c$ (Definition B) or $a - g > D_c$ (Definition A). A packet with $c \le t_{\text{sim-limit}}$ that is neither delivered nor dropped by the end of the run is counted here.
   * **Conservation check (new):** `n_valid = n_on_time + n_Drop_Queue + n_Drop_Retry + n_Drop_Other + n_Late_Arrival` must hold for every run and class. A violation means a drop signal is not mapped.
4. **Statistics:** see §1.6.
5. **Telemetry exclusion:** station telemetry is background traffic, throttled by design in TAS cells. It is excluded from the primary metric and reported in a secondary throughput/loss panel.

### 1.6 Statistical treatment and sample sizes
* **Unit of analysis is the replication.** For each (cell, N, λ, class) compute one miss rate per replication, then the mean and a Student-t confidence interval over replications (Jain). Packets within a run are correlated (queue drops come in bursts), so a Wilson interval on pooled packets understates variance.
* **Wilson is kept only as an upper bound when all replications have $k = 0$**, and is labelled approximate. Report the raw counts $(k_{\text{miss}}, n_{\text{total}})$ next to it.
* **Replication count** comes from Jain's relative half-width formula in the Phase 9 pilot.

Sample sizes with 55 s of measured time (60 s limit, 5 s warmup), 10 replications, and the Wilson 95% upper bound for $k = 0$:

| N (AMRs) | State pkts/run | State pooled (10 reps) | Upper bound (State) | Orders pkts/run | Orders pooled (10 reps) | Upper bound (Orders) |
| :---: | ---: | ---: | :---: | ---: | ---: | :---: |
| 5 | 2,750 | 27,500 | 1.4e-4 | 1,375 | 13,750 | 2.8e-4 |
| 10 | 5,500 | 55,000 | 7.0e-5 | 2,750 | 27,500 | 1.4e-4 |
| 20 | 11,000 | 110,000 | 3.5e-5 | 5,500 | 55,000 | 7.0e-5 |
| 40 | 22,000 | 220,000 | 1.8e-5 | 11,000 | 110,000 | 3.5e-5 |

DDS: 22,000 packets per run if each of the 4 stations sends one 100 Hz flow (to be confirmed by Q7).

**Percentile reporting rule:** report p99 only if the pooled $n \ge 10^4$ and p99.9 only if $n \ge 10^5$. Otherwise flag the value as "insufficient samples" (for example Orders at N = 5 has about 14 samples beyond p99.9).

### 1.7 Reporting rule: miss versus deadline
Because the deadline values are placeholders (Q2) and the single-deadline metric is nearly degenerate with them (§1.9), the lookup tables store the empirical CDF, and the primary result is reported as a **miss-rate curve over $D \in \{1, 2, 5, 10, 20, 50\}\ \text{ms}$** for Definitions A and B, with the class deadline of Q2 marked on the curve. The twin can then apply whatever $D_c$ and tick rule the maintainers confirm, without re-simulating.

### 1.8 DDS resonance mitigation
Station DDS has a nominal period of $10\ \text{ms}$, identical to $T$. With a fixed period each station's phase relative to the tick grid is static, which creates an all-or-nothing artifact for $L = 0$ and still affects tail events when $L = D$.
* **Resolution:** jitter the DDS period by $\pm 5\%$ (`uniform(9.5ms, 10.5ms)`). The phase then random-walks (step standard deviation about 0.29 ms, about 1,200 packets to wander one tick). Also randomize the tick-grid phase $\phi \sim \text{uniform}(0, T)$ per replication.

### 1.9 Finding F1: the primary metric is almost degenerate with the placeholder parameters (analytic, Oct 13)
* **Wired late arrivals are impossible for the 50 ms classes.** With a 100 Mbps link and an 80-packet queue, the maximum queueing delay is $80 \times 117.6\ \mu\text{s} \approx 9.4\ \text{ms}$, well below $D = 50\ \text{ms}$. State and Orders can only be dropped in the wired domain, never late.
* **FIFO at 74.7 Mbps** (wire load about 78.4 Mbps plus State, $\rho \approx 0.8$): overflow probability of an 80-packet queue is negligible.
* **FIFO at 149.3 Mbps** (about 160 Mbps offered into 100 Mbps): about 37% of arrivals are dropped, State included. This is the only wired regime that produces misses.
* **TAS:** telemetry is capped at 44.8 Mbps of payload and is dropped by design at 74.7 and 149.3 Mbps. The State window is only 20% occupied at N = 40.
* **Wireless at 54 Mbps:** at most 18% utilization at N = 40 (capacity.md).

Expected result: of the 72 grid points (6 cells × 4 N × 3 λ), only the 8 points of Cells 1 and 2 at λ = 149.3 Mbps should leave zero, and only for State. The bottleneck-migration hypothesis would not be observable.

Actions (status **Open**, linked to Q8 and checklist A3): (i) report miss-vs-D (§1.7); (ii) densify λ near the knee (about 80 to 100 Mbps); (iii) add PHY rate (12 or 6 Mbps) and/or N up to 80 to 120 as factors; (iv) run a sensitivity with tighter $D$ for State and Orders. This is an analytic estimate and must be confirmed by the pilot.

---

## 2. Key Questions for Supervisors & Digital Twin Maintainers

| Q# | Topic | Date Sent | Addressee | Status | Date Adopted | Working Assumption |
| :---: | :--- | :---: | :--- | :---: | :---: | :--- |
| **Q1** | Tick period and consumption rule | Oct 13, 2026 | Prof. Antônio / Twin Maintainers | Pending (partial) | Oct 12, 2026 | $T = 10\ \text{ms}$; $L_c = D_c$. |
| **Q2** | Class deadlines $D_c$ | Oct 13, 2026 | Prof. Antônio / Twin Maintainers | Pending (partial) | Oct 12, 2026 | Orders: 50 ms; State: 50 ms; DDS: 5 ms; Telemetry: 100 ms. |
| **Q3** | Lookup table format and interpolation | Oct 13, 2026 | Twin Maintainers | Pending (partial) | Oct 12, 2026 | Internal schema in §5; JSON/CSV; PCHIP/nearest-neighbor. |
| **Q4** | L4 fidelity (UDP abstraction) | Oct 13, 2026 | Prof. Antônio | Adopted; confirmation pending | Oct 12, 2026 | Open-loop UDP in P2 (§3). |
| **Q5** | Factory scale (fleet bounds, stations, link speeds) | Oct 13, 2026 | Prof. Antônio | Pending | Oct 12, 2026 | 4 stations, 100 Mbps backbone, 802.11g, fleet sweep 5 to 40 AMRs. |
| **Q6** | Real VDA 5050 message sizes and rates (split from Q5) | Oct 13, 2026 (inside Q5) | Prof. Antônio | Pending | Oct 12, 2026 | State 1000 B at about 10 Hz; Orders 600 B at 5 Hz (exponential). |
| **Q7** | DDS flow matrix and FMS role (new) | To send | Prof. Antônio / Twin Maintainers | Not sent | n/a | Station *i* sends to station *(i+1) mod 4*; FMS is not a DDS subscriber. |
| **Q8** | Grid extension and deadline sensitivity (new) | To send | Prof. Antônio | Not sent | n/a | Keep the 6 × 4 × 3 grid; add miss-vs-D curves and a 12 Mbps PHY sensitivity. |

### Per-question notes: closed on our side, still missing

**Q1.** *Closed on our side:* $T = 10\ \text{ms}$ is consistent in the proposal and the guide; the formula and the effect of $L_c = D_c$ are verified (§1.3). Storing the eCDF makes the tables independent of the final rule. *Still missing:* confirmation of $T$ and the formula for $c$; whether the test is $a \le c$ or $a < c$; what the NER does with a late event (discard, use previous state, or block the clock), which decides whether a miss is binary; whether $L_c$ is per class.

**Q2.** *Closed on our side:* the proposal (§3.4) defines the deadlines as experimental modeling parameters, so the defaults above are valid as our modeling choice. Reporting is protected by the miss-vs-D curve (§1.7). *Still missing:* a process-level source. The 50/5/50/100 ms values come from the implementation guide without citation.

**Q3.** *Closed on our side:* internal schema and interpolation rules (§5). Only the converter depends on the answer. *Still missing:* NER runtime/language, size and query-latency limits, whether it consumes full eCDFs or only percentiles, out-of-grid policy, versioning.

**Q4.** *Closed on our side:* methodological justification is complete. Open-loop UDP keeps the offered load (the independent variable) identical across FIFO, priority and TAS. Add to threats to validity: real MQTT/TCP adds retransmissions and head-of-line blocking (tails are underestimated) and 20 to 40 B of extra header per frame. *Still missing:* only the supervisor's confirmation, which blocks nothing.

**Q5.** *Still missing:* real fleet bounds, number of stations, link speeds. Supervisor only.

**Q6.** *Still missing:* serialized sizes of real VDA 5050 `order` and `state` messages; the state periodicity rule in VDA 5050 v3.0.0 (the guide states a 1 Hz minimum and 10 Hz for high-precision supervision, unverified); the source of the guide's figures (206 B base, 154 B per node, 434 B per edge), which are unreferenced. The VDA 5050 factsheet schema carries protocol limits (maximum MQTT message length, nodes and edges per order, minimum order interval) that can bound the ranges.

**Q7.** *Why it matters:* telemetry only shares an egress port with State (§4). DDS is unaffected in every cell unless the FMS is one of its destinations. *Still missing:* who talks to whom in DDS and whether the FMS subscribes.

**Q8.** *Why it matters:* §1.9. *Still missing:* the advisor's view on adding PHY rate as a fifth table dimension, on extending N to 80 to 120, and on reporting miss-vs-D as the primary result.

---

## 3. Core Architectural Decisions

| Decision | Choice | Status | Rationale |
| :--- | :--- | :---: | :--- |
| **Switch Placement** | `TsnSwitch` behind `AccessPoint` (`amr <-> ap <-> tsnSwitch <-> fms/stations`) | Decision | INET's `AccessPoint` lacks TAS egress queues. A switch behind the AP produces measurable gate-admission delay on uplink traffic entering the wired backbone. |
| **L2 Addressing** | Flat L2 domain with `GlobalArp` enabled | Decision | Prevents ARP broadcasts from skewing initial frame latencies. |
| **Offered Load Parity** | `rng-0` (protocols) vs `rng-1` (generators) | Decision (to verify) | Intended to guarantee identical offered load across all 6 cells for a given seed. Verify in Step 4.4. Note: AMR initial positions use `uniform()` on rng-0, which also feeds the MAC. If `ScheduledDcf` consumes rng-0 differently at init, positions can differ between cells. Map positions to a dedicated stream or fix them per seed. |
| **Buffer Sizing Budget** | Total 80 packets across all wired configs | Decision | FIFO: 1 × 80 queue; Priority and TAS: 4 × 20 queues. Parity is in packet count, not in bytes (`dataCapacity`); byte sensitivity is a Phase 9 item. |
| **802.1Q Tag Stripping** | `excludeEncapsulationProtocols = ["ieee8021qctag"]` on `tsnSwitch` egress | Decision | Prevents tagged frames (0x8100) toward the AP or untagged endpoints. Frame overhead is 70 B with the tag and 66 B without. Window capacities are unchanged either way (§6). |
| **MAC Learning** | `RelayInterfaceLearner` on `tsnSwitch` | Decision | AMR MAC addresses reside behind the AP bridge and cannot be configured statically. |
| **Stationary AMRs** | `StationaryMobility` in the manufacturing hall | Decision | Aligned with proposal §1 scope. |
| **Transport fidelity** | Open-loop UDP for all classes (Q4) | Proposed | Keeps offered load independent of the queueing discipline. Threats to validity are listed under Q4. |
| **Radio channel** | Error-free by scope: noise floor $-110\ \text{dBm}$, 20 mW, 2.412 GHz | Proposed | The proposal excludes detailed propagation, so $-110\ \text{dBm}$ is an intentional choice, not a mistake. The earlier claim that $-95\ \text{dBm}$ guarantees errors does not hold: at 42.4 m with free-space loss the SNR is 35 dB at 20 mW, still error-free at 54 Mbps. Errors only appear with $-95\ \text{dBm}$ plus InF-NLOS loss (SNR 23.5 to 25.7 dB at 20 mW) or 2 mW. Keep $-95\ \text{dBm}$ as an optional sensitivity configuration. |
| **Statistical unit** | Replication (per-replication rate, Student-t CI) | Proposed | Packets within a run are correlated (§1.6). |
| **Primary result format** | Miss-vs-D curves for Definitions A and B | Proposed | Protects the study from the placeholder deadlines (§1.7, §1.9). |
| **Lookup schema** | Internal tidy CSV plus JSON mirror (§5) | Proposed | Decouples our output from the answer to Q3. |
| **Telemetry generator process** | Poisson (`exponential(${telInterval})`) in Point & Sweep; initial offset `uniform(0s, ${telInterval})` | Decision | Adopted Poisson arrival process in all configurations: at $\rho \approx 0.8$ it forms a queue due to variance/clustering, representing the most conservative case for FIFO best-effort buffering (whereas periodic D/D/1 arrivals can artificially suppress queueing). Interval (2 ms, 600 µs, 300 µs) is per station (4 stations produce 22.4, 74.7, 149.3 Mbps aggregate payload, matching capacity.md). Initial offset scaled to `uniform(0s, ${telInterval})` ensures the 4 stations are desynchronized at $t=0$ across all arrival rates. |
| **Grid design** | λ near the knee, PHY rate factor, N up to 80 to 120 | **Open** | See §1.9 and Q8. |

---

## 4. Topology facts: who shares which egress port

| Switch egress port | Traffic carried | Shares with telemetry? |
| :--- | :--- | :---: |
| switch to FMS | Telemetry (4 stations) and State (uplink from the AP) | **Yes** |
| switch to AP | Orders only | No |
| switch to station *i* | DDS addressed to station *i* | No (unless the FMS is a DDS destination, Q7) |
| AP to switch (AP egress, plain FIFO) | State, at most about 3.4 Mbps at N = 40 | No |

Station NIC egress is shared by DDS and telemetry. At 300 µs, telemetry is about 39 Mbps per station, below the 100 Mbps link, and head-of-line blocking is at most one 117.6 µs frame.

Consequences:
* Orders and DDS never queue behind telemetry. The statement in the guide that FIFO causes "massive drops of orders" does not follow from this topology.
* Under TAS, Orders can only get worse than under FIFO (gate wait up to 900 µs). The TSN benefit appears for State, and for telemetry itself (throttled by design).
* Under 802.1Q priority, Orders see the same latency as under FIFO, because their port carries nothing else.

---

## 5. Lookup-table internal schema (our side of Q3)

**Dimensions:** `cell` ∈ {1..6} (categorical), `N_AMR` ∈ {5, 10, 20, 40, [80]}, `lambda_tel_Mbps` ∈ {22.4, 74.7, 149.3} (to be densified, §1.9), `class` ∈ {orders, dds, state, telemetry} (categorical).

**Main table** (one row per combination): `n_total`, `n_reps`, `n_miss_A(D)`, `n_miss_B(D)` for each $D$ in §1.7, `p_loss`, counts per bin (`Drop_Queue`, `Drop_Retry`, `Drop_Other`, `Late_Arrival`), per-replication mean and Student-t half-width of the miss rate, delay quantiles p50, p90, p95, p99, p99.9 (each flagged when $n$ is below the rule in §1.6).

**eCDF table** (long format): `cell, N_AMR, lambda_tel_Mbps, class, quantile_level, delay_ms`, with at least 20 levels (denser in the tail). Lost packets are stored as `p_loss`, not as a delay.

**Formats:** CSV (tidy) as the source, JSON as a mirror. HDF5 only if the maintainers ask (Q3).

**Interpolation rules:**
* `cell` and `class` are never interpolated.
* `N_AMR` and `lambda_tel_Mbps`: monotone PCHIP applied per quantile level; nearest neighbor in saturation regions (FIFO above 100 Mbps of wire load, telemetry above the TAS ceiling of 44.8 Mbps).
* The miss rate for any $(D, T, L)$ is **recomputed from the interpolated eCDF**, not interpolated directly.
* Never extrapolate outside the grid: clamp to the edge and flag the value.

---

## 6. Analytic checks (Oct 13, 2026)

| Check | Result |
| :--- | :--- |
| 802.11g exchange times (capacity.md §1) | Reproduced at 54, 24, 12 and 6 Mbps: state 326/522/882/1606 µs, order 266/390/618/1074 µs, scheduled 258/454/814/1538 µs. The 326 µs figure requires two 6 µs signal extensions (data and ACK). **Verified (analytic).** INET calibration is still pending (checklist C5). |
| Wireless utilization table | Reproduced (18% at N = 40, 54 Mbps; 92% at N = 200). |
| GCL windows | Disjoint, total 1000 µs. Offsets 0/900/700/500 µs give [0,100), [100,300), [300,500), [500,1000) µs under the INET `PeriodicGate` semantics (offset = initial position in the cycle). Confirm with a gate trace. |
| Frames per window and ceilings | 1/9/2/4 frames and 4.8/14.4/16/44.8 Mbps. The same with 66 B or 70 B overhead. |
| Window occupancy | State: N·10/2000 (20% at N = 40, 100% at N = 200). Orders: N·5/1000 (100% at N = 200). |
| Wired offered load | Reproduced (70 B overhead includes the 4 B 802.1Q tag). Telemetry: 22.4, 74.7, 149.3 Mbps payload for 4 stations at 2 ms, 600 µs, 300 µs. |
| FIFO maximum drain | $80 \times 1470\ \text{B}$ at 100 Mbps is 9.4 ms. |
| Link budget at 42.4 m | See §3 (radio channel row). |

---

## 7. Sync items for the other documents

**parameters.md**
* §4 Background noise: relabel from "Optimistic" to "intentional, error-free channel by scope"; add $-95\ \text{dBm}$ as a sensitivity configuration.
* §4 Transmitter power and carrier frequency: adopt 20 mW and 2.412 GHz (INET defaults).
* §6 Telemetry: define a single generator process (§3 open row) and the offset `uniform(0, interval)` for each λ.
* §6 DDS: add the flow matrix after Q7.
* §8: note that wire sizes are 70 B with the 802.1Q tag and 66 B after stripping.
* §9 Phase Offset to TAS: change from "0 µs, Decision" to "Open, derive from the latency chain" (checklist C6).
* Cite the Implementation Guide section that actually exists (§5.1 is not in the guide file received).

**capacity.md** (generated by `analysis/capacity.py`)
* The reference to "decisions.md Q6" is now valid (Q6 = real VDA 5050 sizes and rates).
* Regenerate with INET-measured exchange times after C5.


