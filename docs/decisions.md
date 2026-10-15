# Matrix Factory Twin: Architectural Decisions & Questions Log

**Revision:** Oct 14, 2026 (Q1–Q8 closure: maintainer ground truth for the NER engine, two-tier deadline framework, lookup-table schema and 24-quantile interpolation rules, open-loop UDP lock, VDA 5050 sizing, Option 7B DDS routing, and 2-level PHY rate sweep). Previous revision: Oct 13, 2026 (comprehensive reference update with citations, normative standards, and analytical derivations). All architectural and experimental questions Q1–Q8 are formally locked.

### Status Vocabulary
* **Decision**: Adopted in the model, validated analytically, awaiting experimental simulation test.
* **Proposed**: Recommended in the Oct 13 technical review, awaiting final supervisory confirmation.
* **Open**: Unresolved requirement that cannot be closed without external input (tracked in [`docs/checklist_secao3.md`](checklist_secao3.md)).
* **Verified (analytic)**: Recomputed and verified mathematically against protocol specs and INET 4.7.0 architecture on Oct 13, 2026. INET runtime execution confirmation required where noted.
* **Confirmed (maintainer)**: Confirmed by the Matrix Factory Twin maintainers against the twin's source code (`MainSimulator.java`, `BaseStationArtifact.java`, `AMRArtifact.java`, `TimerArtifact.java`, `DatabaseArtifact.java`) on Oct 14, 2026.
* **Closed**: Question fully answered; only documented follow-ups remain.

---

## Changelog (Oct 14 Revision: Q1–Q5 Closure)
1. **Q1 closed (maintainer ground truth):** The twin runs a variable-step conservative NER engine with a finest simulated quantum $T_{\min} = \text{MIN\_DT} = 10\ \text{ms}$ and a macro step $\text{MAX\_DT} = 1000\ \text{ms}$. The consumption rule $c = \lceil (g + L_c)/T \rceil \cdot T$ and the non-strict boundary $a \le c$ are confirmed. The clock never stalls on a late packet. `TICK_QUORUM_TIMEOUT_MS = 10` is a wall-clock thread barrier, not a simulated tick (§1.1, §1.3, new §1.3.1).
2. **Late-arrival semantics are class-dependent (new §1.3.1):** State and Telemetry follow Zero-Order Hold (stale snapshot reused, late update consumed at $c' = \lceil a/T \rceil \cdot T$); Orders and DDS are consumed late while $a \le g + \text{TTL}$ and discarded (equivalent to a drop) beyond the TTL. Added the discrete staleness measure $\Delta k_{\text{stale}}$ and the counting rule that separates physical loss from late arrival (§1.5 item 6).
3. **Open note (new §1.3.2):** The maintainers describe $L_c = T$ for State/Telemetry freshness deadlines, while this log's working choice is $L_c = D_c$ for all classes. Both variants are computed offline from the stored eCDF; confirmation requested.
4. **Q2 decided (two-tier deadline framework, §1.7):** Tier 1 keeps the normative industrial budgets as indicator markers on continuous Miss-vs-$D$ curves; Tier 2 records the twin's own watchdog TTLs ($\text{TTL}^{\text{app}}_c$) separately. The standard deadline spectrum is extended with $D = 100\ \text{ms}$ (Telemetry marker). The numeric TTL constants are still requested from the maintainers.
5. **Q3 decided (maintainers aligned):** Two-table export (`lookup_summary`, `lookup_ecdf`) in tidy CSV plus JSON mirror; quantile-space (horizontal) interpolation with monotone PCHIP; clamping without extrapolation; stochastic inverse-transform consumption with per-flow seeded PRNGs (§5.3–§5.5). Quantile grid locked to the explicit 24-level list.
6. **Q4 decided:** Open-loop UDP for all classes and all six cells, with the framing-overhead bound and the threat-to-validity statement documented (§2 Q4 dossier, §3, §6).
7. **Corrections to the working-session text:** (a) the "24-point" and "≥ 20 points" quantile statements were inconsistent with the explicit level list and are superseded (§5.3); (b) the TCP-vs-UDP overhead is 12 to 24 B, i.e. 1.1 to 2.2 % of a State frame, not only 1.1 %; the claim that GCL frame ceilings are unaffected holds for State and Orders but not for a hypothetical TCP-framed DDS flow (DDS is natively UDP, so it is not affected in the model) (§6); (c) literature citations that could not be verified were not adopted (§8).
8. **Q5 decided (approved Oct 14):** Controlled scale model kept: 4 stations, $100\ \text{Mbps}$ backbone, one 802.11g cell at $54\ \text{Mbps}$. The AMR fleet sweep is extended to $N \in \{5, 10, 20, 40, 80\}$. The $200\ \text{m} \times 200\ \text{m}$ hall, central AP and stationary AMRs within $\pm 30\ \text{m}$ (maximum $42.43\ \text{m}$ from the AP) are kept, with a dedicated spatial RNG stream (§2 Q5 dossier, §3, §6).
9. **Correction to the Q5 working-session text:** it quoted the offered wired load at $N = 40$ as $\{23.9, 81.8, 160.2\}\ \text{Mbps}$. The $23.9\ \text{Mbps}$ value is the $N = 5$ figure; at $N = 40$ it is $26.9\ \text{Mbps}$ ($\rho \approx 0.27$, not $0.24$), per `capacity.md` §4 (§6). Also, $N = 80$ reaches only $37\,\%$ wireless utilization at $54\ \text{Mbps}$, so strong CSMA contention still depends on the PHY-rate sensitivity of Q8.
10. **Q6–Q8 fully locked (Oct 14):** Q6 locked to realistic VDA 5050 message sizes (State 1000 B, Orders 600 B). Q7 locked to Option 7B DDS routing (`station[*] -> fms:5100` at 100 Hz +/- 5% jitter). Q8 locked to 2-level PHY rate sweep (54 Mbps and 12 Mbps) with 10 repetitions per point.

---

## Changelog (Oct 13 Revision)
1. **§1.3 & §1.4 (Metric Formulations):** Mathematical proof and derivation of Definition B under lead time $L_c = D_c$: available slack $s = c - g$ is uniformly distributed over $[D_c, D_c + T)$, proving that $\text{delay} > D_c$ is a necessary but not sufficient condition for a miss ($\text{Miss}_B \le \text{Miss}_A$). Removed invalid alternative $L_c = T - D_c$ ($L_c < 0$ for $D_c > T$). Corrected $L=0$ baseline formulation to $\mathbb{E}[\min(\text{delay}, T)]/T$.
2. **§1.5 & §1.6 (Counting Rules & Statistics):** Loss attribution establishes a mutually exclusive and exhaustive classification schema (`Drop_Queue`, `Drop_Retry`, `Drop_Other`, `Late_Arrival`) with packet conservation laws. Demoted Wilson score intervals to a zero-occurrence ($k=0$) upper bound (rule of three); established replication-level Student-$t$ confidence intervals as the primary statistical unit (Jain, 1991). Sample size bounds and percentile reporting thresholds ($p_{99} \implies n \ge 10^4$, $p_{99.9} \implies n \ge 10^5$) formalized.
3. **§1.9 (Finding F1 - Degenerate Metric Analysis):** Formally proved that with $D = 50\text{ ms}$, 100 Mbps backbone, and 80-packet buffer, maximum wired queuing delay is $80 \times 117.6\ \mu\text{s} \approx 9.408\ \text{ms} \ll D$. State and Orders never arrive late on the wire. At 54 Mbps, wireless medium utilization is $\le 18\%$ at $N=40$. Result: 64 out of 72 baseline points yield zero misses. Added mandatory mitigations: continuous Miss-vs-$D$ curves ($D \in \{1, 2, 5, 10, 20, 50\}\text{ ms}$), telemetry knee densification, and wireless PHY/fleet sensitivity.
4. **§2 (Questions Log Q1–Q8):** Added exhaustive normative citations (3GPP TS 22.104, 5G-ACIA, VDA 5050 v3.0.0, OMG DDS v1.4, RFC 768/9293). Split Q5 into Q5 (Factory Scale) and Q6 (VDA 5050 Message Sizing & Schemas). Added Q7 (DDS Flow Matrix & Port Contention) and Q8 (Grid Extension & Degeneracy Mitigation). Added detailed per-question technical dossiers with mathematical formulations, trade-offs, and closed vs. open boundaries.
5. **§3 (Core Architectural Decisions):** Expanded each architectural decision with technical depth, parameters, INET 4.7.0 module paths, mathematical validations (link budget at 42.4 m, queue drainage equations, framing overheads), and normative references.
6. **§4 (Topology Interference Matrix):** Formalized switch egress port sharing. Proved that Orders and DDS never share an egress queue with background telemetry, demonstrating that TSN priority/TAS benefits apply exclusively to State traffic under current topology.
7. **§5 (Lookup Table Schema):** Detailed tidy CSV and JSON mirror schema, dimension specifications, and monotone PCHIP interpolation rules (Fritsch & Carlson, 1980).
8. **§6 & §7 (Analytic Checks & Sync):** Synchronized all analytical constants with [`docs/parameters.md`](parameters.md), [`docs/capacity.md`](capacity.md), and [`simulations/omnetpp.ini`](../simulations/omnetpp.ini). Added comprehensive normative references catalog (§8).

---

## 1. Primary Evaluation Metric: Deadline Miss Formulations

### 1.1 Mathematical Notation
* $g \in \mathbb{R}^+$: Packet generation/creation timestamp at the application layer of the source host.
* $a \in \mathbb{R}^+ \cup \{\infty\}$: Packet delivery/arrival timestamp at the application layer of the destination host ($a = \infty$ if the packet is dropped due to queue overflow, retry exhaustion, or simulation termination).
* $T \in \mathbb{R}^+$: Digital twin discrete NER tick period. The twin uses a variable step $\Delta t \in [10\ \text{ms}, 1000\ \text{ms}]$; its finest quantum is $T_{\min} = 10\ \text{ms}$ ($100\ \text{Hz}$, `MIN_DT`). Definition B is evaluated on a uniform grid with primary $T = T_{\min} = 10\ \text{ms}$ and offline sensitivity at $T \in \{50, 500\}\ \text{ms}$ (§1.3.1).
* $D_c \in \mathbb{R}^+$: Application-layer deadline threshold for traffic class $c$.
* $L_c \in \mathbb{R}$: Application-layer lead time offset for traffic class $c$.
* $\text{delay} = a - g$: End-to-end network latency ($\text{delay} = \infty$ for undelivered packets).
* $c \in \{k \cdot T \mid k \in \mathbb{N}\}$: Scheduled discrete consumption instant within the digital twin execution engine.
* $\text{TTL}_c \in \mathbb{R}^+$: Protocol watchdog/time-to-live enforced by the twin's `TimerArtifact` for control and coordination transactions (Orders, DDS). Numeric constants are requested from the maintainers (Q2, §2).
* $\Delta k_{\text{stale}} \in \mathbb{N}$: Discrete staleness (excess Age of Information, in ticks) of a delivered State/Telemetry packet: $\max\big(0, \lceil a/T \rceil - \lceil (g + L_c)/T \rceil\big)$.

---

### 1.2 Definition A: Continuous Relative Deadline (Baseline Metric)
$$\text{Miss}_A = \begin{cases} 1 & \text{if packet is lost } (a = \infty) \text{ or } (a - g) > D_c \\ 0 & \text{if } a \le g + D_c \end{cases}$$

#### Methodological Characteristics & Citations
* **Decoupling from Simulator Grid:** Definition A depends strictly on physical network lifetime ($a - g$). It evaluates pure transport performance independent of the digital twin's internal discrete-event time management (HLA IEEE 1516-2010 [10]).
* **Reconstruction from Delay Distributions:** Because Definition A requires only the scalar delay, it can be evaluated directly from standard cumulative distribution functions (eCDF) or delay histograms without logging individual generation timestamps $g$.
* **Reporting Requirement:** Definition A is reported for every traffic class, network configuration (Cells 1–6), and parameter sweep level as the fundamental continuous-time baseline.
* **Physical meaning in the twin (maintainer-confirmed, Oct 14):** When the variable-step engine advances directly to $t_{\text{req}} = g + L_c$ (possible whenever $g + L_c$ lies within $[\text{MIN\_DT}, \text{MAX\_DT}]$ of the current time and no earlier event intervenes), the consumption instant is $c = g + L_c$. With $L_c = D_c$ this makes Definition A exact for unconstrained variable-step ticks. Definition B is exact when concurrent agent events pin the engine to its finest quantum.

---

### 1.3 Definition B: Discrete Tick Grid Consumption Instant (Digital Twin Ingestion)
The digital twin Next Event Request (NER) engine advances time in discrete steps of period $T$. An application event generated at $g$ with class lead time $L_c$ is scheduled for consumption at the discrete grid boundary:
$$c = \left\lceil \frac{g + L_c}{T} \right\rceil \times T$$
$$\text{Miss}_B = \begin{cases} 1 & \text{if packet is lost } (a = \infty) \text{ or } a > c \\ 0 & \text{if } a \le c \end{cases}$$

#### Adopted Design Choice: Class Lead Time Equals Deadline ($L_c = D_c$)
*(Status: **Decision**. The ceiling formula for $c$ and the non-strict boundary $a \le c$ are **Confirmed (maintainer)**, Oct 14, 2026. The class-specific value $L_c = D_c$ is this study's working choice; see the open note in §1.3.2.)*

#### Formal Analytical Derivation & Proof of Slack Dynamics
1. **Available Time Slack:** Let $s = c - g$ denote the physical time elapsed between packet generation $g$ and the discrete consumption instant $c$. Substituting $L_c = D_c$:
   $$s = \left\lceil \frac{g + D_c}{T} \right\rceil \times T - g$$
2. **Bounds on Slack:** By the mathematical definition of the ceiling function $\lceil x \rceil = x + (1 - (x \bmod 1))$:
   $$s \in [D_c,\, D_c + T)$$
   If packet generation phase $(g \bmod T)$ is uniformly distributed over the interval $[0, T)$, the available slack $s$ is uniformly distributed:
   $$s \sim \mathcal{U}(D_c,\, D_c + T)$$
3. **Necessary vs. Sufficient Condition:**
   Because $s \ge D_c$ for all packets, a packet whose transfer delay satisfies $D_c < \text{delay} \le s$ arrives **before** the consumption tick $c$ and is consumed on time. Consequently:
   * $\text{delay} > D_c$ is a **necessary, but not sufficient**, condition for a deadline miss under Definition B.
   * For every individual packet, $\text{Miss}_B \le \text{Miss}_A$.
   * Across any sample of traffic, the aggregate miss rate under Definition B is strictly less than or equal to Definition A:
     $$\mathbb{E}[\text{Miss}_B] \le \mathbb{E}[\text{Miss}_A]$$
4. **Continuous Expectation Integral:**
   Assuming network delay is a random variable independent of generation phase $u = (g \bmod T) \sim \mathcal{U}(0, T)$:
   $$P(\text{Miss}_B) = \frac{1}{T} \int_0^T P(\text{delay} > D_c + x)\, dx \qquad (\text{with } P(\text{delay} > y) = 1 \text{ for lost packets})$$
   For a deterministic network delay $\tau$:
   $$P(\text{Miss}_B) = \frac{\min\big(\max(\tau - D_c,\, 0),\, T\big)}{T}$$
   *Proof:* If $\tau \le D_c$, $P(\text{Miss}_B) = 0$. If $\tau \ge D_c + T$, $P(\text{Miss}_B) = 1$. For intermediate values $D_c < \tau < D_c + T$, the packet misses only if generated during the fractional window of length $\tau - D_c$, yielding a linear miss probability $(\tau - D_c)/T$.
5. **Interpretation:** Definition B with $L_c = D_c$ represents an application-centric, phase-smoothed twin metric that absorbs network jitter within the residual tick slack.

#### Elimination of the Candidate Alternative $L_c = T - D_c$
The heuristic $L_c = T - D_c$ previously proposed in preliminary working notes has been **formally rejected**:
* For classes where $D_c > T$ (e.g., State and Orders with $D_c = 50\ \text{ms}$, $T = 10\ \text{ms}$), it yields a negative lead time $L_c = -40\ \text{ms}$. A negative lead time schedules consumption in the past relative to generation ($c < g$), which is physically nonsensical.
* The formulation $L_c = T - D_c$ is mathematically valid only under the restricted condition $D_c \le T$. For DDS ($D_c = 5\ \text{ms}$, $T = 10\ \text{ms}$), $T - D_c = 5\ \text{ms}$, which coincides exactly with $L_c = D_c$. Therefore, $L_c = D_c$ generalizes universally across all parameter regimes.

---

### 1.3.1 Maintainer Ground Truth for the NER Engine (Q1, Oct 14, 2026)
*(Status: **Confirmed (maintainer)**, derived from the Time Management Component and artifact code.)*

| Item | Maintainer answer | Code reference |
| :--- | :--- | :--- |
| Simulated tick | Variable-step conservative NER: $\Delta t = \operatorname{clip}\big(\min_i (t_{\text{req},i} - t_{\text{now}}),\ 10\ \text{ms},\ 1000\ \text{ms}\big)$. No simulated tick is shorter than $T_{\min} = 10\ \text{ms}$. | `MainSimulator.tickLoop()`, `MIN_DT`, `MAX_DT` (`MainSimulator.java:56-57, 260-266`) |
| Active AMR step | Active AMRs request `soonestNeed = min(0.5, max(dwellRemaining, 0.05))`, i.e. steps of $50\ \text{ms}$ to $500\ \text{ms}$. | `AMRArtifact.updatePositions()` (`AMRArtifact.java:495, 499`) |
| Idle / macro step | $1000\ \text{ms}$ ($1\ \text{Hz}$) when no sooner NER is pending; also the electricity spot-price update cadence. | `MAX_DT` |
| Quorum constant | `TICK_QUORUM_TIMEOUT_MS = 10` is a **wall-clock** thread barrier (`nerLatch.await(10, ms)`) for the 13 JaCaMo agents, not a simulated duration. On timeout the TMC increments `droppedNerCount` and advances time anyway. | `MainSimulator.java:55, 255-258` |
| Consumption instant | Target timestamp $t_{\text{req}} = g + L_c$ is consumed at the first tick $c = k \cdot T \ge t_{\text{req}}$, i.e. $c = \lceil (g + L_c)/T \rceil \cdot T$ (exact on a uniform grid). | `MainSimulator.java:422-428`; e.g. `BaseStationArtifact.java:202`, `AMRArtifact.java:499` |
| Boundary | Non-strict: the Time Advance Grant fires when `time >= entry.requestedNextTime()`, so $a \le c$ is on time. | `issueTimeAdvanceGrant(double, int)` |
| Clock stall | Never. A late event does not block simulated time. | `MainSimulator.java:255-258` |

**Consequences for evaluation.** Definition B uses $T = T_{\min} = 10\ \text{ms}$ as primary. Because the lookup tables store the full delay eCDF, $\text{Miss}_B(T)$ is evaluated offline for $T = 50\ \text{ms}$ (minimum active AMR step) and $T = 500\ \text{ms}$ (nominal cell-traversal step) without re-running OMNeT++:
$$P(\text{Miss}_B(T)) = \frac{1}{T}\int_0^T P(\text{delay} > L_c + x)\,dx.$$

**Late-arrival semantics ($c < a < \infty$), by traffic class.** The twin never stalls; the behaviour depends on whether the class is a state snapshot or a TTL-guarded transaction. The KILL / skip / queue distinction follows the deadline-miss handling strategies analysed for logical-execution-time controllers [16].

| Traffic class | Late behaviour in the twin | Mechanism | Metric treatment |
| :--- | :--- | :--- | :--- |
| **State** (VDA 5050, AMR → FMS) and **Telemetry** (OPC UA/MQTT, Station → FMS) | **Zero-Order Hold.** Tick $c$ reuses the previous snapshot; the delayed update takes effect at $c' = \lceil a/T \rceil \cdot T$ unless a newer sample overwrites it. | `assembleTelemetryFrame()` reads volatile snapshots (`MainSimulator.java:301-420`) | $\text{Miss}_B = 1$ at tick $c$; graded staleness $\Delta k_{\text{stale}}$ for surviving packets. |
| **Orders** (VDA 5050, FMS → AMR) and **DDS** (Station → Station) | **Delayed consumption** at the first tick $c' \ge a$ while $a \le g + \text{TTL}$; **discarded** (KILL, identical to a drop) once $a > g + \text{TTL}$. | Pending `nerRegistry` entries; `TimerArtifact.evaluateTTLs()` (`MainSimulator.java:274`); `cancelTransport` (`AMRArtifact.java:234`); `recordWatchdogFired` (`DatabaseArtifact.java:181`) | $\text{Miss}_B = 1$ at tick $c$; functional discard rate $P(\text{delay} > \text{TTL}_c)$ evaluated offline from the eCDF once the TTL constants are known. |

The code distinguishes two meanings of $D_c$: for control/coordination packets it is the protocol timeout ($c = \lceil (g + D_c)/T \rceil \cdot T$, late packets killed by the watchdog); for periodic state/telemetry it is a freshness deadline (see the open note in §1.3.2).

---

### 1.3.2 Open Note: Lead Time of State and Telemetry (to confirm with maintainers)
The maintainers' practical rule states $L_c = T$ for the periodic State/Telemetry classes, whereas this log adopts $L_c = D_c$ for all four classes (§1.3). With $L_c = T = 10\ \text{ms}$ the State slack is $s \in [10, 20)\ \text{ms}$, much tighter than $D_{\text{state}} = 50\ \text{ms}$. Both readings are computed offline from the stored eCDF, so nothing has to be re-run:
* **Definition B (primary):** $L_c = D_c$.
* **Definition B$^{T}$ (maintainer variant, State and Telemetry only):** $L_c = T$, $P(\text{Miss}_B^{T}) = \frac{1}{T}\int_0^T P(\text{delay} > T + x)\,dx$.

**Action:** ask the maintainers which reading the twin implements for State (freshness horizon $D_{\text{state}}$, or consumption at the immediately following tick).

---

### 1.4 Pitfall of Definition B with Zero Lead Time ($L_c = 0$)
If lead time is omitted ($L_c = 0$), consumption is pinned to the immediate next tick:
$$c = \left\lceil \frac{g}{T} \right\rceil \times T$$
The available time window is $s = c - g = T - (g \bmod T) \in (0, T]$. If generation phase $u = (g \bmod T)$ is uniformly distributed over $[0, T)$:
$$P(\text{Miss}_B \mid L=0) = \frac{1}{T} \int_0^T P(\text{delay} > x)\, dx = \frac{\mathbb{E}[\min(\text{delay}, T)]}{T}$$
Only in the special case where all delays are strictly bounded below $T$ does this simplify to $\mathbb{E}[\text{delay}]/T$.

#### Detrimental Consequences of $L_c = 0$:
1. **Severe Artificial Miss Rates:** A deterministic, jitter-free transmission delay of only $2\ \text{ms}$ produces a constant **$20\%$ deadline miss rate** ($2\text{ ms} / 10\text{ ms} = 0.20$), purely as an artifact of discrete tick quantization.
2. **Degradation of TSN Valuation:** Because the metric collapses to mean delay divided by $T$, it completely obscures the determinism, bounded jitter, and tail-latency guarantees provided by IEEE 802.1Qbv Time-Aware Shaper (TAS) and scheduled wireless access.
3. **Resolution:** Unconditionally adopt $L_c = D_c$ for discrete twin evaluation, and report Definition A as the baseline.

---

### 1.5 Accounting Rules, Horizon Filters, and Packet Conservation Laws
To guarantee statistical integrity without sampling bias:
1. **Warmup Transient Filter:** Discard all packets generated prior to transient stabilization:
   $$\text{Filter Condition: } g < t_{\text{warmup}} \quad (t_{\text{warmup}} = 5.0\ \text{s})$$
2. **Unbiased Horizon Filter:** Packet delivery must not be truncated arbitrarily at simulation cutoff $t_{\text{sim-limit}} = 60\ \text{s}$. Filtering on arrival time $a$ introduces severe right-censoring bias by favoring faster packets. Instead, filter strictly on scheduled consumption instant $c$:
   $$\text{Filter Condition: } c > t_{\text{sim-limit}}$$
   Because $c$ depends exclusively on generation timestamp $g$ and deterministic lead time $L_c$, filtering by $c$ is statistically independent of network latency $\text{delay}$. For $D_c = 50\ \text{ms}$ and $T = 10\ \text{ms}$, this safely excludes packets generated within the final $60\ \text{ms}$ of simulation time.
3. **Causal Loss Attribution Schema (Mutually Exclusive & Exhaustive):**
   Every generated packet surviving the warmup and horizon filters must be accounted for in exactly one category:
   * `On_Time`: Delivered with $a \le c$ (Definition B) or $a - g \le D_c$ (Definition A).
   * `Late_Arrival`: Delivered successfully, but $a > c$ (Definition B) or $a - g > D_c$ (Definition A). Packets with $c \le t_{\text{sim-limit}}$ that remain in-flight at simulation termination are classified here.
   * `Drop_Queue`: Discarded at switch, access point, or host network interfaces due to buffer overflow (`packetDropQueueOverflow`).
   * `Drop_Retry`: Discarded at wireless MAC layer due to IEEE 802.11 retry counter exhaustion (`packetDropRetryLimitReached`).
   * `Drop_Other`: Discarded due to physical layer corruption, bit errors, or interface down events (`packetDrop`). Expected to be zero under the baseline error-free channel scope.
4. **Fundamental Conservation Law:**
   For every simulation run, traffic class, and experimental configuration, the total generated packet volume must satisfy:
   $$n_{\text{valid}} = n_{\text{On\_Time}} + n_{\text{Late\_Arrival}} + n_{\text{Drop\_Queue}} + n_{\text{Drop\_Retry}} + n_{\text{Drop\_Other}}$$
   Any deviation indicates an unmapped INET signal or telemetry leakage.
5. **Telemetry Traffic Exclusion:** Station background telemetry ($1400\ \text{B}$ frames) represents unprioritized Best Effort coexistence load. In TAS configurations (Cells 5 and 6), telemetry is intentionally throttled by the GCL gate schedule ($500\ \mu\text{s}$ open window per $1\ \text{ms}$ cycle). Telemetry is excluded from the primary deadline miss metric and analyzed in a secondary backbone saturation and throughput panel.
6. **Loss vs. Late-Arrival Separation (Q1):** Physical drops ($p_{\text{loss}} = \text{Drop\_Queue} + \text{Drop\_Retry} + \text{Drop\_Other}$, i.e. $a = \infty$) are always kept separate from delivered-but-late packets (`Late_Arrival`). Because `Late_Arrival` depends on $D_c$, it is derived as $\text{miss\_A}_D - p_{\text{loss}}$ rather than stored as a separate column. This separation lets the twin apply KILL (Orders/DDS beyond TTL) or ZOH (State/Telemetry) without modifying the lookup table. Telemetry is excluded from the primary metric but is reported in the secondary panel with $D_{\text{tel}} = 100\ \text{ms}$.

---

### 1.6 Statistical Treatment, Sample Sizing, and Percentile Reporting
* **Unit of Statistical Independence:** The **simulation replication** is the primary unit of analysis (Jain, 1991 [9]). Packets within a single simulation run exhibit temporal correlation (queuing congestion and buffer drop events occur in correlated bursts). Pooling packet counts across runs violates the independent and identically distributed (i.i.d.) assumption of standard binomial confidence intervals, understating true variance.
* **Confidence Interval Estimation:** For each combination of $(\text{cell}, N, \lambda, \text{class})$, calculate the miss rate $\hat{p}_r$ for each independent replication $r \in \{1, \dots, R\}$. The sample mean $\bar{p}$ and $(1 - \alpha)$ Student-$t$ confidence interval half-width are:
  $$\bar{p} = \frac{1}{R} \sum_{r=1}^R \hat{p}_r, \qquad H = t_{1 - \alpha/2,\, R-1} \cdot \frac{s}{\sqrt{R}}, \qquad s = \sqrt{\frac{1}{R-1}\sum_{r=1}^R (\hat{p}_r - \bar{p})^2}$$
* **Wilson Score Bound for Zero-Miss Regimes:** When all replications yield zero misses ($\sum k_r = 0$), the Student-$t$ variance is degenerate ($s = 0$). In this boundary case, report an approximate $95\%$ upper confidence bound using the Wilson score interval on pooled packets (equivalent to the classical Rule of Three, $3/n_{\text{pooled}}$):
  $$p_{\text{upper}} = \frac{z^2}{n_{\text{pooled}} + z^2} \approx \frac{1.96^2}{n_{\text{pooled}} + 3.84}$$
* **Sample Size Matrix (55 s Measured Window, $R = 10$ Replications):**

| Fleet Size $N$ | State Pkts/Run | State Pooled ($n$) | Wilson 95% Bound ($k=0$) | Orders Pkts/Run | Orders Pooled ($n$) | Wilson 95% Bound ($k=0$) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **5 AMRs** | 2,750 | 27,500 | $1.40 \times 10^{-4}$ | 1,375 | 13,750 | $2.79 \times 10^{-4}$ |
| **10 AMRs**| 5,500 | 55,000 | $6.98 \times 10^{-5}$ | 2,750 | 27,500 | $1.40 \times 10^{-4}$ |
| **20 AMRs**| 11,000| 110,000| $3.49 \times 10^{-5}$ | 5,500 | 55,000 | $6.98 \times 10^{-5}$ |
| **40 AMRs**| 22,000| 220,000| $1.75 \times 10^{-5}$ | 11,000| 110,000| $3.49 \times 10^{-5}$ |
| **80 AMRs**| 44,000| 440,000| $8.73 \times 10^{-6}$ | 22,000| 220,000| $1.75 \times 10^{-5}$ |

* **Tail Percentile Reporting Criteria:**
  * Report $99\text{th}$ percentile ($p_{99}$) latency only when pooled sample size $n \ge 10^4$ (guaranteeing $\ge 100$ samples in the distribution tail).
  * Report $99.9\text{th}$ percentile ($p_{99.9}$) latency only when pooled sample size $n \ge 10^5$ (guaranteeing $\ge 100$ samples in the distribution tail).
  * If $n < 10^5$, explicitly flag $p_{99.9}$ as "insufficient tail samples" (for example, Orders at $N = 5$ has only $\sim 14$ samples beyond $p_{99.9}$).

---

### 1.7 Primary Result Reporting Rule: Continuous Miss-vs-Deadline Curves
Because application deadlines are experimental modeling parameters (Q2) and the single-threshold evaluation metric is nearly degenerate under current placeholders (§1.9), the primary simulation outcome must not be collapsed into a single point estimate.
* **Empirical CDF Curve Reporting:** The lookup tables store the full empirical latency CDF.
* **Continuous Outcome Curves:** Results are reported as continuous miss-rate curves evaluated across a standardized deadline spectrum:
  $$D \in \{1.0,\, 2.0,\, 5.0,\, 10.0,\, 20.0,\, 50.0,\, 100.0\}\ \text{ms}$$
  for both Definition A and Definition B. The nominal operational deadline of Q2 is marked as an indicator point on each curve.
* **Impact:** Decouples experimental results from external deadline revisions; any updated deadline or consumption rule can be evaluated retrospectively without re-running simulations.

#### Two-Tier Deadline Framework (Q2, decided Oct 14, 2026)
* **Tier 1: network transport budget $D^{\text{net}}_c$ (normative reference markers).** The working budgets Orders $50\ \text{ms}$, State $50\ \text{ms}$, DDS $5\ \text{ms}$, Telemetry $100\ \text{ms}$ are experimental modeling parameters, anchored to industrial references (§2, Q2 dossier) and marked as indicator points on the continuous Miss-vs-$D$ curves. Sensitivity markers: State and Orders at $10\ \text{ms}$ and $20\ \text{ms}$. Code-level anchor for the $50\ \text{ms}$ budgets: $0.05\ \text{s}$ is the minimum active AMR kinematic step (`AMRArtifact.java:495`), so a State report or order delayed beyond $50\ \text{ms}$ misses an entire active kinematic update.
* **Tier 2: end-to-end application watchdog $\text{TTL}^{\text{app}}_c$.** The twin's `TimerArtifact` / `tProc` constants (Contract Net Protocol, Two-Phase Commit, `await_station_start`) include agent reasoning and multi-message negotiation rounds, so they are larger than the network slice $D^{\text{net}}_c$. They are recorded separately in `parameters.md` §6.1 once the maintainers provide them. Evaluating the network only at a single large TTL would reduce the miss rate to the drop rate, because wired queueing is bounded by $9.408\ \text{ms}$ (§1.9) and would hide queueing jitter, priority inversion and gate-admission delay. The continuous spectrum plus the stored eCDF let any threshold $\text{TTL}$ be evaluated offline.
* **Reference ranges used for Tier 1 (see §2 Q2 dossier):** AGV guidance/cooperative motion $10$ to $50\ \text{ms}$ (State, Orders); inter-station coordination/interlocking $1$ to $5\ \text{ms}$ (DDS); condition monitoring/telemetry $10$ to $100\ \text{ms}$ (Telemetry). For periodic flows the Update Time / Survival Time view applies [17].

---

### 1.8 DDS Resonance Mitigation & Jittering
In the baseline model, inter-station DDS coordination traffic operates at a nominal frequency of $100\ \text{Hz}$ ($10\ \text{ms}$ period), exactly matching the digital twin tick period $T = 10\ \text{ms}$. If generation is perfectly periodic, a station's phase relative to the tick grid remains entirely static throughout the run, creating severe resonance artifacts (all packets land at the exact same phase within the tick).
* **Adopted Solution:** Inject $\pm 5\%$ uniform period jitter into DDS transmission:
  $$\text{productionInterval} \sim \mathcal{U}(9.5\ \text{ms},\, 10.5\ \text{ms})$$
  The transmission phase performs a continuous random walk across the tick grid with step standard deviation $\sigma \approx 0.289\ \text{ms}$, requiring $\sim 1,200$ packets to wander across an entire $10\ \text{ms}$ tick.
* **Tick Grid Phase Randomization:** Randomize the absolute tick grid initial offset $\phi \sim \mathcal{U}(0, T)$ independently for each simulation replication. Under the variable-step twin engine (§1.3.1) this grid is the offline Definition B evaluation grid; the randomization removes phase locking between periodic sources and that grid.

---

### 1.9 Finding F1: Primary Metric Degeneracy Under Baseline Placeholders (Analytic Proof)
Analytical re-evaluation of network queue dynamics and channel utilization on Oct 13, 2026 revealed that the primary metric is almost entirely zeroed across the baseline parameter grid.

#### Mathematical Proof of Wired Late Arrival Impossibility:
1. **Backbone Parameters:** Wire bitrate $C_{\text{wire}} = 100\ \text{Mbps}$ ($12.5\ \text{MB/s}$). Switch egress queue capacity $B = 80\ \text{packets}$.
2. **Maximum Frame Length:** The largest packet on the wire is telemetry ($1400\ \text{B}$ payload $+ 70\ \text{B}$ framing overhead $= 1470\ \text{B} = 11,760\ \text{bits}$). Serialization delay:
   $$t_{\text{tx\_max}} = \frac{11,760\ \text{bits}}{100 \times 10^6\ \text{bps}} = 117.6\ \mu\text{s}$$
3. **Maximum Queue Drainage Time:** Under full queue saturation, the longest possible time a newly admitted packet can spend waiting in the buffer before transmission is:
   $$t_{\text{queue\_max}} = B \times t_{\text{tx\_max}} = 80 \times 117.6\ \mu\text{s} = 9.408\ \text{ms}$$
4. **Deadline Comparison:** The operational deadline for State and Orders is $D = 50\ \text{ms}$.
   $$t_{\text{queue\_max}} = 9.408\ \text{ms} \ll D = 50\ \text{ms}$$
5. **Deduction:** Packets traversing the wired backbone can **never** arrive late for any deadline $D \ge 10\ \text{ms}$. In the wired domain, packets are either delivered with latency $\le 9.408\ \text{ms}$ or dropped due to buffer overflow.

#### System Load Dynamics Across Configurations:
* **FIFO at 74.7 Mbps Payload ($\lambda = 600\ \mu\text{s}$):** Total offered wire load is $\approx 78.4\ \text{Mbps}$ telemetry $+ 3.4\ \text{Mbps}$ State $= 81.8\ \text{Mbps}$ ($\rho \approx 0.82$). In an $M/M/1/80$ queue with $\rho = 0.82$, buffer overflow probability is:
  $$P_{\text{drop}} = \frac{(1 - \rho)\rho^B}{1 - \rho^{B+1}} \approx \frac{(0.18)(0.82)^{80}}{1 - (0.82)^{81}} \approx 6.4 \times 10^{-8} \approx 0$$
* **FIFO at 149.3 Mbps Payload ($\lambda = 300\ \mu\text{s}$):** Total offered wire load is $\approx 160.2\ \text{Mbps}$ into a $100\ \text{Mbps}$ link ($\rho \approx 1.60$). Buffer overflows persistently, dropping $\approx 37\%$ of all arriving traffic indiscriminately (including State reports).
* **TAS at All Loads (Cells 5 & 6):** Telemetry is restricted to its designated $500\ \mu\text{s}$ GCL window (capacity: 4 frames/cycle $= 44.8\ \text{Mbps}$ payload ceiling). Excess telemetry is dropped at the switch queue by design. The State window ($[300, 500)\ \mu\text{s}$) has an occupancy of only $20\%$ at $N = 40$ AMRs. State packets experience zero drops and queue delay bounded by $< 1\ \text{ms}$.
* **Wireless Medium at 54 Mbps:** With 40 AMRs, aggregate channel utilization is only $18\%$ (capacity analysis §2). CSMA backoff contention and frame collisions are minimal.

#### Resulting Degeneracy:
Of the 72 baseline parameter grid points ($6\ \text{cells} \times 4\ N \times 3\ \lambda$), **only 8 points** (Cells 1 and 2 at $\lambda = 149.3\ \text{Mbps}$) exhibit non-zero miss rates, and exclusively for State traffic. In the remaining 64 points, the miss rate is exactly $0.000\%$. The expected phenomenon of bottleneck migration would fail to manifest in the experimental data.

#### Mandatory Mitigations (Status: Open / In Progress):
1. **Miss-vs-Deadline Evaluation:** Evaluate and plot miss rates over $D \in \{1, 2, 5, 10, 20, 50, 100\}\ \text{ms}$ (§1.7, Q2 two-tier framework). At $D = 2\ \text{ms}$ and $D = 5\ \text{ms}$, queuing delays produce visible, discriminating metrics.
2. **Telemetry Load Densification:** Densify $\lambda$ around the backbone saturation knee ($70\ \text{to } 110\ \text{Mbps}$ payload, e.g., $\{22.4, 45, 60, 74.7, 85, 95, 110, 149.3\}\ \text{Mbps}$).
3. **Wireless Dimension Expansion:** Introduce a lower PHY rate dimension ($12\ \text{Mbps}$ and $24\ \text{Mbps}$, where utilization reaches $48\%$ and $29\%$ at $N=40$) or expand fleet density to $N \in \{80, 120\}$, driving wireless utilization up to $95\%$.
4. **Tighter Operational Baseline:** Evaluate sensitivity with operational deadlines scaled to $D = 10\ \text{ms}$ and $D = 20\ \text{ms}$ for State and Orders.

---

## 2. Key Questions for Supervisors & Digital Twin Maintainers

| Q# | Topic | Addressee | Status | Date Locked | Locked Specification | Codebase / Normative Basis |
| --- | --- | --- | --- | --- | --- | --- |
| **Q1** | Discrete Tick Consumption Rule | Twin Maintainers | **Confirmed (Codebase)** | Oct 14, 2026 | Variable-step NER $\Delta t \in [10\text{ ms}, 1000\text{ ms}]$ (`MIN_DT = 0.01s`); $c = \lceil (g+L_c)/T \rceil \cdot T$ with $L_c = D_c$ and non-strict $a \le c$. Late semantics: **KILL** (discard after watchdog TTL) for Orders/DDS; **ZOH** (stale snapshot reuse, consumed at $\lceil a/T \rceil \cdot T$) for State/Telemetry. Evaluate $T \in \{10, 50, 500\}\text{ ms}$. | `MainSimulator.java`, `AMRArtifact.java`, `BaseStationArtifact.java`, `TimerArtifact.java`; IEEE 1516-2010. |
| **Q2** | Operational Deadlines ($D_c$) | Prof. Antônio / Maintainers | **Decision** | Oct 14, 2026 | Two-tier deadline framework: Normative markers ($D_{\text{orders}}=50\text{ ms}$, $D_{\text{state}}=50\text{ ms}$ [matching $0.05\text{ s}$ `AMRArtifact` min step], $D_{\text{dds}}=5\text{ ms}$, $D_{\text{tel}}=100\text{ ms}$) + continuous Miss-vs-$D$ spectrum $D \in \{1, 2, 5, 10, 20, 50, 100\}\text{ ms}$. | 3GPP TS 22.104 Rel-18, 5G-ACIA, VDA 5050 v3.0.0. |
| **Q3** | Lookup Table Interface Schema | Twin Maintainers | **Confirmed** | Oct 14, 2026 | Dual-table export (`lookup_summary.csv`/`.json` + 24-quantile `lookup_ecdf.csv`/`.json`); 1D Wasserstein quantile interpolation via Monotone PCHIP (`scipy.interpolate.PchipInterpolator`); saturation clamping; zero extrapolation. | Wickham (2014), Fritsch & Carlson (1980), Duan et al. (2026). |
| **Q4** | L4 Transport Fidelity (UDP) | Prof. Antônio | **Decision** | Oct 14, 2026 | Open-loop UDP (`UdpSourceApp`/`UdpSinkApp`) for all 4 classes to preserve exogenous workload invariance (`rng-1`) and avoid TCP HoL blocking on ZOH flows. Payload sizes include L7 headers. | Project Design Proposal §3.4–§3.5; RFC 768; Jain (1991). |
| **Q5** | Factory Operational Scale | Prof. Antônio | **Decision** | Oct 14, 2026 | 4 workstations, $100\text{ Mbps}$ Ethernet backbone (`100Base-TX`), $200\times 200\text{ m}$ hall ($60\times 60\text{ m}$ AMR zone, $d_{\max}=42.43\text{ m}$), fleet sweep $N \in \{5, 10, 20, 40, 80\}$ bracketing the 13 JaCaMo agents. | VDI 2510 / 4451; IEEE 802.3; Project Design Proposal §3.8. |
| **Q6** | VDA 5050 Message Sizing | Prof. Antônio / Team | **Decision** | Oct 14, 2026 | `State`: $1000\text{ B}$ @ $10\text{ Hz}$ (`uniform(90ms, 110ms)`); `Orders`: $600\text{ B}$ @ $5\text{ Hz}$ (`exponential(200ms)`). Validated against VDA 5050 v3.0.0 UTF-8 JSON schemas; unsourced node/edge formula deprecated. | VDA 5050 v3.0.0 `state.schema.json` & `order.schema.json`. |
| **Q7** | DDS Flow Matrix & Jitter | Prof. Antônio / Maintainers | **Decision (Option 7B)** | Oct 14, 2026 | `station[i] -> fms` on UDP port `5100` ($200\text{ B}$ @ $100\text{ Hz}$ with $\pm 5\%$ period jitter `uniform(9.5ms, 10.5ms)`). Routes DDS across contended `switch -> fms` port alongside State and Telemetry. | OMG DDS v1.4 / DDSI-RTPS v2.3; `MatrixFactoryNetwork.ned`. |
| **Q8** | Degeneracy Mitigation & Grid | Prof. Antônio / Team | **Decision** | Oct 14, 2026 | 8-point telemetry knee sweep $\{22.4, 45.0, 60.0, 74.7, 85.0, 95.0, 110.0, 149.3\}\text{ Mbps}$; 5-point fleet sweep $N \in \{5, 10, 20, 40, 80\}$; 2-level PHY factor $\{54, 12\}\text{ Mbps}$; continuous Miss-vs-$D$ curves. | Finding F1 (`decisions.md` §1.9); Bianchi (2000); Jain (1991). |

---

### Per-Question Technical Dossiers: Citations, Boundaries, and Action Items

#### Question Q1: Discrete Tick Period & NER Consumption Rule
* **Formal Inquiry:**
  1. What is the precise discrete event tick period $T$ (nominal: $10\ \text{ms}$)?
  2. What is the mathematical formulation for event consumption instant $c$? Does it follow $c = \lceil (g + L_c)/T \rceil \cdot T$ with class-dependent lead time $L_c = D_c$?
  3. Is the delivery deadline evaluated via non-strict inequality $a \le c$ or strict inequality $a < c$?
  4. What semantic action does the NER engine execute upon receiving a late packet ($a > c$): is the packet discarded, is stale state from the prior tick reused, or does the simulation clock block until arrival? (Determines whether a deadline miss is binary or graded).
* **Normative References & Context:**
  * **IEEE Std 1516-2010 (HLA):** High Level Architecture time management specifications [10]. Next Event Request (NER) and Time Advance Request (TAR) services advance simulation federates in discrete time increments, consuming events bucketed into the granted time interval.
  * **Proposal Reference:** Project Design Proposal §3.6 ("Primary Metric: Application Deadline-Miss Rate") [13].
* **Closed on Our Side:** Analytical proof that $T = 10\ \text{ms}$ with $L_c = D_c$ provides mathematically robust slack dynamics ($s \in [D_c, D_c + T)$), preventing the severe quantization collapse observed when $L_c = 0$ (§1.4). Full empirical CDF delay distributions are recorded, ensuring that if maintainers require a different tick formulation, the miss rate can be calculated retrospectively without re-running simulations.
* **Resolution (Oct 14, 2026, Confirmed by maintainers):** See §1.3.1. Tick: variable-step NER with $T_{\min} = 10\ \text{ms}$; consumption $c = \lceil (g + L_c)/T \rceil \cdot T$; non-strict $a \le c$; the clock never stalls; late State/Telemetry follow ZOH, late Orders/DDS are consumed until their TTL and then discarded. The $10\ \text{ms}$ quorum constant is wall-clock only.
* **Still Missing (non-blocking):** Which lead time the twin applies to State/Telemetry ($L_c = D_c$ vs. $L_c = T$, §1.3.2); both variants are computed offline.
* **Response cutoff:** Oct 26, 2026 (P1). $T$, the $c$ rule and $a \le c$ are locked now; no further action is needed for them.

---

#### Question Q2: Application Deadlines ($D_c$) per Traffic Class
* **Formal Inquiry:** What are the operational latency deadlines $D_c$ dictated by physical manufacturing constraints, robotic kinematics, and fleet supervision?
* **Normative References & Industry Benchmarks:**
  * **3GPP TS 22.104 v18.4.0 (Rel-18) [1]:** *Service requirements for cyber-physical control applications in vertical domains.* Table 5.2-1 specifies automated guided vehicle (AGV) cooperative motion control latency at $10\ \text{to } 50\ \text{ms}$ (transfer interval $10\ \text{to } 50\ \text{ms}$, message size $100\ \text{to } 1000\ \text{B}$, survival time $20\ \text{ms}$). Factory motion control requires $0.5\ \text{to } 2\ \text{ms}$. Table 5.3-1 specifies condition monitoring / telemetry latency at $10\ \text{to } 100\ \text{ms}$.
  * **5G-ACIA White Papers [2, 3]:** *5G for Automation in Industry* (3rd Ed., 2021) and *Integration of 5G with TSN for Industrial Automation* (2021). Autonomous mobile robot (AMR) guidance and fleet control benchmark latency: $20\ \text{to } 50\ \text{ms}$. Inter-robot / station safety interlock latency: $\le 5\ \text{ms}$.
  * **VDA 5050 v3.0.0 (2026) [4]:** Interface between AGVs and fleet control. Section 6.2 state heartbeat and dynamic obstacle avoidance.
* **Physical Kinematic Basis:** For an AMR operating at velocity $v = 1.5\ \text{m/s}$ with emergency braking deceleration $a_{\text{brake}} = 2.0\ \text{m/s}^2$, a communication latency $\tau = 50\ \text{ms}$ contributes $\Delta d = v \cdot \tau = 0.075\ \text{m} = 7.5\ \text{cm}$ to total reaction travel before brake actuation. A latency $\tau > 100\ \text{ms}$ causes protective field violations and emergency stop tripping.
* **Closed on Our Side:** Project Proposal §3.4 explicitly designates deadlines as experimental modeling parameters. The working baseline of Orders: $50\ \text{ms}$, State: $50\ \text{ms}$, DDS: $5\ \text{ms}$, and Telemetry: $100\ \text{ms}$ is formally justified as our experimental design choice, fully protected by continuous Miss-vs-$D$ reporting (§1.7).
* **Resolution (Oct 14, 2026, Decision):** Two-tier framework adopted (§1.7): Tier 1 keeps the normative budgets as indicator markers on continuous Miss-vs-$D$ curves over $D \in \{1, 2, 5, 10, 20, 50, 100\}\ \text{ms}$; Tier 2 records the twin's own $\text{TTL}^{\text{app}}_c$ separately. Reference ranges: AGV guidance $10$ to $50\ \text{ms}$ (State, Orders), interlocking $1$ to $5\ \text{ms}$ (DDS), monitoring $10$ to $100\ \text{ms}$ (Telemetry).
* **Still Missing:** The numeric constants of `TimerArtifact.evaluateTTLs()`, `BaseStationArtifact.java` (`tProc`), `AMRArtifact.java` (`cancelTransport`) and `DatabaseArtifact.java` (`recordWatchdogFired` for CNP, 2PC, `await_station_start`), and confirmation of the freshness horizon of State ($50\ \text{ms}$ vs. the minimum active AMR step). Plant-specific physical confirmation from the twin team also remains open.

---

#### Question Q3: Lookup Table Interface & NER Ingestion Format
* **Formal Inquiry:**
  1. What programming language and runtime environment executes the digital twin NER engine (e.g., C++, Python, Java, Rust)?
  2. What are the memory limits and query latency bounds for runtime table lookups?
  3. Does the twin ingest full empirical CDF quantiles or discrete percentiles ($p_{50}, p_{95}, p_{99}, p_{99.9}$)?
  4. What interpolation policy is executed outside discrete grid points: Monotone PCHIP, multilinear, or nearest-neighbor?
  5. What metadata schema and versioning headers are required?
* **Normative References & Methods:**
  * **Tidy Data Principles (Wickham, 2014) [12]:** Structured CSV schema where each variable is a column and each observation is a row.
  * **Monotone PCHIP Interpolation (Fritsch & Carlson, 1980) [11]:** Piecewise Cubic Hermite Interpolating Polynomials preserve monotonicity and eliminate overshoot in empirical latency tails.
* **Closed on Our Side:** Comprehensive internal tidy CSV and JSON mirror schema defined (§5). Python data export module (`analysis/export_lookup.py`) specified.
* **Resolution (Oct 14, 2026):** The maintainers reported that our recommendations are aligned, so the schema and interpolation rules of §5 are adopted. The twin is a Java/JaCaMo system with seeded deterministic replay; consumption is by seeded inverse-transform sampling (§5.5).
* **Still Missing:** Execution of the automated ingestion test with a 1-cell, 1-$N$, 1-$\lambda$ sample file (checklist C3), the preferred format (CSV vs. JSON) and the resource-tree location loaded at startup, and the runtime memory/latency bounds.

---

#### Question Q4: L4 Transport Layer Fidelity (Open-Loop UDP vs. MQTT/TCP)
* **Formal Inquiry:** Confirmation of open-loop UDP transport for VDA 5050 and telemetry flows during Phase 2.
* **Normative References & Standards:**
  * **RFC 768 [7]:** User Datagram Protocol (UDP).
  * **RFC 9293 [8]:** Transmission Control Protocol (TCP) and RFC 5681 (TCP Congestion Control).
  * **VDA 5050 v3.0.0 Section 5 [4]:** Standard specification mandates MQTT v3.1.1/v5.0 over TCP/TLS.
* **Methodological Rationale for Open-Loop UDP:**
  * **Preservation of Independent Variable:** A central scientific objective of this study is comparing queueing disciplines (FIFO vs. 802.1Q Priority vs. 802.1Qbv TAS) under identical offered load conditions. Open-loop UDP maintains traffic arrival instants strictly independent of network performance.
  * **Feedback Coupling Distortion:** Closed-loop TCP couples traffic generation to network latency via window-based congestion control (AIMD/slow-start), flow control, and retransmission timeouts. A congested FIFO switch would artificially throttle TCP traffic sources, reducing offered load and making cross-cell comparative evaluation mathematically invalid.
  * **Threats to Validity (Documented for Final Report):** Open-loop UDP measures pure L2/L3 transport latency and loss. It excludes TCP handshakes, head-of-line blocking and retransmission timeouts, so results are lower bounds on latency tails for protocols that would run over MQTT/TCP. Replacing TCP (20 B base header, 32 B with timestamps) by UDP (8 B) removes $12$ to $24\ \text{B}$ of L4 framing per packet, i.e. $0.96$ to $1.92\ \mu\text{s}$ at $100\ \text{Mbps}$ ($1.1$ to $2.2\,\%$ of a $1070\ \text{B}$ State frame; $0.8$ to $1.6\,\%$ of a $1470\ \text{B}$ Telemetry frame). Application payload sizes are defined inclusive of the L7 protocol header (MQTT/RTPS/UADP).
* **Native Transport Audit:** DDS/RTPS and OPC UA PubSub (UADP) are natively UDP, so open-loop UDP is an exact match. VDA 5050 State/Orders are natively MQTT over TCP/TLS (QoS 0 for State), so UDP is a deliberate methodological abstraction.
* **Resolution (Oct 14, 2026, Decision):** Open-loop UDP (`UdpSourceApp`/`UdpSinkApp`) is locked for all four classes in all six cells. Reasons: (1) closed-loop TCP would throttle sources differently in each cell (FIFO at $\lambda_{\text{tel}} = 149.3\ \text{Mbps}$ drops about $37\,\%$ of arriving traffic), destroying offered-load parity and paired seeds (Jain [9]); (2) TCP head-of-line blocking would deliver an obsolete State packet while holding a fresher one, which conflicts with the ZOH consumption confirmed in Q1; (3) TCP retransmissions would turn `Drop_Queue`/`Drop_Retry` into long RTO delay spikes and double-count recovery already handled by the twin's TTL watchdogs; (4) a central MQTT broker would add a second pass through the switch and measure broker queueing instead of the wireless-to-wired bottleneck, so the FMS is modeled as the endpoint (AMR → AP → tsnSwitch → FMS). The proposal already defines synthetic generators with protocol parameters fixed at implementation time (§3.4, §3.5), so no proposal change is required. Prof. Antônio is informed through the E0 package.

---

#### Question Q5: Factory Operational Scale & Topology Parameters
* **Formal Inquiry:** Confirmation of realistic physical bounds for AMR fleet density, workstation node count, and backbone link speeds.
* **Standards & Planning Guidelines:**
  * **VDI 2510 & VDI 4451:** Automated Guided Vehicle Systems (AGVS) planning and design guidelines.
  * **Proposal Scope:** Baseline parameters (4 workstations, $100\ \text{Mbps}$ backbone, single IEEE 802.11g AP, fleet sweep $5$ to $80$ AMRs after the Oct 14 decision).
* **Resolution (Oct 14, 2026, Decision, approved by the team; Prof. Antônio informed via E0):**
  1. **Scale model kept:** $\text{numStations} = 4$, $100\ \text{Mbps}$ backbone, 802.11g at $54\ \text{Mbps}$ baseline. At $N = 40$ the offered wired load ($26.9$, $81.8$, $160.2\ \text{Mbps}$ for the three telemetry levels) gives $\rho \approx 0.27$, $0.82$, $1.60$, bracketing the FIFO saturation knee. At $1\ \text{Gbps}$ the $74.7\ \text{Mbps}$ point would give $\rho \approx 0.08$ and no wired queueing, invalidating the study's core hypothesis (bottleneck migration).
  2. **Fleet sweep** $N \in \{5, 10, 20, 40, 80\}$. The twin runs 13 JaCaMo agents, so its AMR count lies inside the grid and is resolved by interpolation without extrapolation (the exact split of stations and AMRs is still to be confirmed). $N = 80$ is the upper stress point: $37\,\%$ wireless utilization at $54\ \text{Mbps}$ and $95\,\%$ at $12\ \text{Mbps}$ (`capacity.md` §2). It does not reach strong contention at $54\ \text{Mbps}$ on its own; contention regimes depend on the PHY-rate sensitivity of Q8.
  3. **Geometry:** $200\ \text{m} \times 200\ \text{m}$ hall, AP at $(100, 100)$, stationary AMRs at $100\ \text{m} \pm \mathcal{U}(-30, 30)\ \text{m}$ (a $60\ \text{m} \times 60\ \text{m}$ square, at most $42.43\ \text{m}$ from the AP and $84.85\ \text{m}$ apart). All nodes are within mutual carrier-sense range (§6), which removes hidden terminals so that wireless delay depends on fleet density and DCF contention. AMR coordinates use a dedicated RNG stream, separate from `rng-0`, so positions are identical in `Radio_CSMA` and `Radio_Sched` for a given seed (checklist C8).
  4. **Side effects:** the baseline grid grows from $6 \times 4 \times 3 = 72$ to $6 \times 5 \times 3 = 90$ points; the scheduled-wireless superframe at $N = 80$ is $48\ \text{ms}$, close to the $50\ \text{ms}$ deadline (checklist C6); the $N = 80$ sample sizes are in §1.6.
* **Still Missing (non-blocking):** The canonical numbers of stations and AMRs in the Matrix Factory Twin (the 13 agents are not broken down), and supervisor confirmation of the layout dimensions. The typical island and plant fleet sizes attributed to VDI 2510 / 4451 in the working session are unverified and are not used as evidence.

---

#### Question Q6: Real VDA 5050 Message Sizing & Serialization Schemas
* **Formal Inquiry:** Empirical serialized message lengths and transmission frequencies for VDA 5050 `order` and `state` topics.
* **Normative Analysis of VDA 5050 v3.0.0 JSON Schemas [4]:**
  * **`state` Topic (`.../state`):** Contains header metadata, orderId, orderUpdateId, lastNodeId, driving flag, operatingMode, agvPosition ($x, y, \theta$, mapId, deviationRange), velocity ($v_x, v_y, \omega$), batteryState (charge, voltage, health), nodeStates array, edgeStates array, errors array, and safetyState.
    * *Minimal State:* Base structure without trajectory history serializes to $\approx 600\ \text{to } 800\ \text{B}$ of UTF-8 JSON.
    * *Nominal State:* Standard active navigation payload with node/edge progress measures $\approx 950\ \text{to } 1200\ \text{B}$. Baseline **1000 B** represents an accurate empirical midpoint.
  * **`order` Topic (`.../order`):** Contains header metadata, orderId, orderUpdateId, nodes array (nodeId, sequenceId, nodePosition, actions), and edges array (edgeId, sequenceId, startNodeId, endNodeId, trajectory knots, actions).
    * *Minimal Order (1 node, 1 edge):* $\approx 450\ \text{B}$.
    * *Standard Move Order (2 nodes, 1 edge, NURBS trajectory):* $\approx 600\ \text{B}$.
    * *Complex Order (5 nodes, 4 edges, multiple actions):* $\approx 1200\ \text{to } 1800\ \text{B}$. Baseline **600 B** represents a standard single-hop dispatch order.
  * **Factsheet Protocol Limits (`.../factsheet`):** The VDA 5050 factsheet defines protocol constraints: `protocolLimits.maxMessageSize` (typically $64\ \text{KB}$), `protocolLimits.maxOrderNodes`, and minimum inter-order timing.
  * **Resolution (Oct 14, 2026, Decision):** State: $1000\text{ B}$ @ $10\text{ Hz}$ (`uniform(90ms, 110ms)`); Orders: $600\text{ B}$ @ $5\text{ Hz}$ (`exponential(200ms)`). Validated against VDA 5050 v3.0.0 UTF-8 JSON schemas; unsourced node/edge formula deprecated.

---

#### Question Q7: DDS Flow Matrix & FMS Subscription Role
* **Formal Inquiry:** What is the exact publish-subscribe topology for inter-station DDS coordination? Does the central FMS node subscribe to DDS topics?
* **Normative References & Standards:**
  * **OMG DDS v1.4 [5]:** Data Distribution Service for Real-Time Systems.
  * **DDSI-RTPS v2.3:** Real-Time Publish-Subscribe Wire Protocol.
* **Architectural Impact (Topology Port Contention Matrix §4):**
  * *Unicast Ring (Option 7A):* Station $i$ publishes strictly to Station $(i+1) \pmod 4$.
  * *Option 7B (Locked):* Station $i$ sends DDS coordination traffic directly to FMS on port `5100` ($200\text{ B}$ @ $100\text{ Hz}$ with $\pm 5\%$ period jitter `uniform(9.5ms, 10.5ms)`). Routes DDS across the contended `tsnSwitch -> fms` port alongside State and Telemetry, activating priority and TAS gating discrimination.
* **Resolution (Oct 14, 2026, Decision - Option 7B):** `station[i] -> fms` on UDP port `5100` ($200\text{ B}$ @ $100\text{ Hz}$ with $\pm 5\%$ period jitter `uniform(9.5ms, 10.5ms)`). Routes DDS across contended `tsnSwitch -> fms` port alongside State and Telemetry.

---

#### Question Q8: Parameter Grid Extension & Degeneracy Mitigation
* **Formal Inquiry:** Approval of proposed mitigations for Finding F1 (§1.9): Reporting continuous Miss-vs-$D$ curves, densifying telemetry offered load near the backbone saturation knee ($70\ \text{to } 110\ \text{Mbps}$), and introducing wireless PHY rate sensitivity ($12\ \text{Mbps}$ and $24\ \text{Mbps}$) or expanding fleet sweep up to $N = 80\ \text{to } 120$.
* **Resolution (Oct 14, 2026, Decision):** 8-point telemetry knee sweep $\{22.4, 45.0, 60.0, 74.7, 85.0, 95.0, 110.0, 149.3\}\text{ Mbps}$; 5-point fleet sweep $N \in \{5, 10, 20, 40, 80\}$; 2-level PHY factor $\{54, 12\}\text{ Mbps}$; continuous Miss-vs-$D$ curves.

---

## 3. Core Architectural Decisions

| Decision | Selected Implementation | Status | Formal Rationale & Normative Citations |
| :--- | :--- | :---: | :--- |
| **Switch Placement** | `TsnSwitch` behind `AccessPoint` (`amr <-> ap <-> tsnSwitch <-> fms/stations`) | Decision | INET's `AccessPoint` module implements a standard Ethernet MAC without TAS egress queues. Placing `TsnSwitch` behind the AP enforces IEEE 802.1Qbv gating on uplink traffic entering the wired backbone [6]. |
| **L2 Addressing** | Flat L2 domain with `GlobalArp` enabled | Decision | Flat addressing domain (`10.0.x.x/16`) eliminates initial ARP request/response transients and broadcast storm delays (`assignDisjunctSubnetAddresses = false`). |
| **Offered Load Parity** | RNG stream isolation: `rng-0` (protocols) vs. `rng-1` (traffic generators) | Decision (to verify) | Guarantees identical packet generation timestamps across all six cells for a given seed. Isolated AMR spatial coordinates to a dedicated stream to prevent MAC DCF interaction (Step 4.4). |
| **Buffer Sizing Budget** | Total 80 packets across all wired switch configurations | Decision | Enforces strict buffer space parity: FIFO utilizes $1 \times 80$ queue; Priority and TAS utilize $4 \times 20$ queues. Sensitivity to byte capacity (`dataCapacity`) reserved for Phase 9. |
| **802.1Q Tag Stripping** | `excludeEncapsulationProtocols = ["ieee8021qctag"]` on `tsnSwitch` egress | Decision | Prevents sending 802.1Q tagged frames (EtherType `0x8100`) toward the AP or untagged stations. Frame overhead is 70 B with tag, 66 B without tag. Window capacities are identical (§6). |
| **MAC Address Learning** | `RelayInterfaceLearner` enabled on `tsnSwitch` | Decision | INET's `TsnSwitch` disables MAC learning when stream features are active. AMR MACs reside behind the AP bridge and cannot be configured statically; dynamic learning prevents broadcast flooding. |
| **Stationary AMRs** | `StationaryMobility` in $200\ \text{m} \times 200\ \text{m}$ manufacturing hall | Decision | Excludes spatial fast fading and shadowing transients, isolating MAC channel contention and queuing phenomena (Project Proposal §1 scope [13]). |
| **Transport Fidelity** | Open-loop UDP across all traffic classes (Q4) | Decision | Preserves offered load as a strictly independent variable across FIFO, Priority, and TAS cells (Jain [9]); avoids TCP head-of-line blocking and RTO masking of drop causes. Framing-overhead bound and threat to validity documented in the Q4 dossier and §6. |
| **Radio Channel Scope** | Error-free channel by scope: $P_{\text{tx}} = 20\ \text{mW}$, $2.412\ \text{GHz}$, noise floor $-110\ \text{dBm}$ | Proposed | Proposal excludes detailed multipath propagation. Link budget proof at 42.4 m confirms error-free operation. Industrial floor noise ($-95\ \text{dBm}$) retained as optional sensitivity. |
| **Statistical Unit** | Replication-level mean and Student-$t$ confidence intervals | Proposed | Packets within a run exhibit temporal correlation; replication-level aggregation satisfies statistical independence (Jain, 1991 [9]). Wilson score retained for $k=0$. |
| **Primary Result Format**| Continuous Miss-vs-Deadline curves ($D \in \{1, 2, 5, 10, 20, 50, 100\}\ \text{ms}$) for Definitions A and B, with the Tier 1 budgets as markers (Q2) | Decision | Resolves metric degeneracy (Finding F1, §1.9) and insulates results from unconfirmed deadline placeholders (Q2). Twin watchdog TTLs are recorded as Tier 2. |
| **Lookup Table Schema** | Two tidy tables (`lookup_summary`, `lookup_ecdf`) in CSV with JSON mirror (§5); quantile-space interpolation with monotone PCHIP | Decision | Maintainers aligned (Oct 14). Follows Tidy Data principles [12]; PCHIP [11]; Wasserstein quantile interpolation [18, 19]. |
| **Telemetry Process** | Poisson arrival process (`exponential(${telInterval})`) per station; desynchronized offset | Decision | Poisson arrivals induce queuing bursts at $\rho \approx 0.8$, providing the conservative benchmark for FIFO. Dynamic initial offset `uniform(0s, ${telInterval})` guarantees desynchronization. |
| **Radio Scheduled Spike**| `ScheduledDcf` with dynamic superframe sizing and MAC TDMA gating (Spike S1) | Open | Replaces static 100 ms superframe with dynamic sizing ($N=5..120$); preserves air-time parity with CSMA while eliminating collisions (Checklist C6). |
| **Tick & Consumption Semantics** | Variable-step NER with $T_{\min} = 10\ \text{ms}$; $c = \lceil (g + L_c)/T \rceil T$; on time iff $a \le c$; no clock stall | Confirmed (maintainer) | `MainSimulator.java:56-57, 260-266, 422-428`. Primary Definition B at $T = 10\ \text{ms}$, offline sensitivity at $50$ and $500\ \text{ms}$ (§1.3.1). |
| **Late-Arrival Semantics** | State/Telemetry: ZOH and delayed consumption at $\lceil a/T \rceil T$. Orders/DDS: delayed consumption until $g + \text{TTL}$, then discard | Confirmed (maintainer) | `assembleTelemetryFrame()`, `TimerArtifact.evaluateTTLs()`. The table stores $p_{\text{loss}}$ and the finite delay eCDF separately so the twin can apply either rule (§1.5 item 6). |
| **Lookup Consumption Mode** | Stochastic inverse-transform sampling with a per-flow seeded PRNG; summary (expected-value) mode kept as fallback | Decision | Keeps `SeededReplaySeed1Test` deterministic under multi-threaded agent scheduling (§5.5). |
| **Factory Scale & Topology** | 4 stations, $100\ \text{Mbps}$ wired, 802.11g at $54\ \text{Mbps}$; fleet sweep $N \in \{5, 10, 20, 40, 80\}$ (Q5) | Decision | Controlled scale model: keeps the backbone near saturation so bottleneck migration can be observed (Jain [9]); $\rho \approx 0.27 / 0.82 / 1.60$ at $N = 40$. $N = 80$ is the stress point; PHY-rate sensitivity is handled in Q8. |
| **Spatial Layout** | $200\ \text{m} \times 200\ \text{m}$ hall, AP at $(100, 100)$, stationary AMRs within $\pm 30\ \text{m}$; dedicated spatial RNG stream (Q5) | Decision | Maximum AP distance $42.43\ \text{m}$, maximum AMR-to-AMR distance $84.85\ \text{m}$, both well above the sensitivity margin (§6): no hidden terminals. Stream isolation in checklist C8. |

---

### Detailed Mathematical Justifications for Key Decisions

#### Radio Link Budget & Channel Feasibility at 42.4 m Max Distance
* **Parameters:** Transmitter power $P_{\text{tx}} = 20\ \text{mW} = +13.01\ \text{dBm}$. Center frequency $f = 2.412\ \text{GHz}$ ($\lambda = c/f = 0.1243\ \text{m}$). Max AMR distance $d = \sqrt{30^2 + 30^2} \approx 42.43\ \text{m}$.
* **Free-Space Path Loss (FSPL):**
  $$\text{FSPL}(d) = 20\log_{10}(d) + 20\log_{10}(f) + 20\log_{10}\left(\frac{4\pi}{c}\right) \approx 20\log_{10}(42.43) + 20\log_{10}(2.412 \times 10^9) - 147.55 \approx 72.64\ \text{dB}$$
* **Received Signal Power ($P_{\text{rx}}$):**
  $$P_{\text{rx}} = P_{\text{tx}} - \text{FSPL} = +13.01\ \text{dBm} - 72.64\ \text{dB} = -59.63\ \text{dBm}$$
* **Signal-to-Noise Ratio (SNR) Analysis:**
  1. *Baseline Scope ($-110\ \text{dBm}$ Noise Floor):*
     $$\text{SNR} = -59.63\ \text{dBm} - (-110.0\ \text{dBm}) = 50.37\ \text{dB}$$
     Well above the INET demodulation threshold ($\text{snirThreshold} = 4\ \text{dB}$) and the $\sim 25\ \text{dB}$ required for 54 Mbps 64-QAM 3/4 ERP-OFDM, guaranteeing an error-free channel.
  2. *Realistic Industrial Floor ($-95\ \text{dBm}$ Noise Floor, Free Space):*
     $$\text{SNR} = -59.63\ \text{dBm} - (-95.0\ \text{dBm}) = 35.37\ \text{dB}$$
     Still provides $> 10\ \text{dB}$ fade margin above the 54 Mbps demodulation threshold.
  3. *3GPP TR 38.901 Industrial Factory NLOS (InF-NLOS) [6]:*
     Path loss model $\text{PL} = 32.4 + 31.8\log_{10}(d) + 20\log_{10}(f) = 32.4 + 51.75 + 7.65 = 91.8\ \text{dB}$.
     $$P_{\text{rx}} = +13.01 - 91.8 = -78.79\ \text{dBm}$$
     $$\text{SNR}_{\text{InF}} = -78.79 - (-95.0) = 16.21\ \text{dB}$$
     At $16.2\ \text{dB}$, 54 Mbps ERP-OFDM cannot decode (requires $\approx 25\ \text{dB}$), inducing heavy packet corruption. This confirms that channel errors manifest only when combining industrial noise with InF multipath shadowing.

---

## 4. Topology Contention Matrix: Egress Port Interference Analysis (Option 7B Locked)

| Physical Switch Egress Port | Traffic Classes Carried | Traversed by Telemetry? | Contention & Scheduling Implications (Option 7B Locked) |
| --- | --- | --- | --- |
| **`tsnSwitch -> fms`** | **DDS (`TC 2`) + State (`TC 1`) + Telemetry (`TC 0`)** | **YES** | **Primary Wired Bottleneck:** Carries inter-station DDS ($400\text{ pkts/s}$, $D=5\text{ ms}$), AMR State ($10N\text{ pkts/s}$, $D=50\text{ ms}$), and Station Telemetry ($22.4\text{–}149.3\text{ Mbps}$). Under FIFO, queuing delay reaches $9.408\text{ ms}$ at saturation, causing both **late-arrival deadline misses for DDS ($5\text{ ms} < \text{delay} \le 9.408\text{ ms}$)** and buffer overflow drops (`Drop_Queue`) for both DDS and State. Under 802.1Q Priority (Cells 3, 4) and 802.1Qbv TAS (Cells 5, 6), both DDS (`[100, 300) us`) and State (`[300, 500) us`) are isolated from telemetry congestion. |
| **`tsnSwitch -> ap`** | **Orders (`TC 3`)** | **NO** | **Dedicated Downlink Port:** Carries only FMS-to-AMR dispatch orders ($0.13\text{–}2.14\text{ Mbps}$ for $N=5\text{–}80$). Zero contention with telemetry; in TAS cells, experiences at most $900\ \mu\text{s}$ gate admission delay. |
| **`ap -> tsnSwitch`** | **State (`TC 1`)** | **NO** | **Dedicated Uplink Trunk:** Carries only wireless-to-wired AMR State reports ($0.4\text{–}6.8\text{ Mbps}$ for $N=5\text{–}80$) into the switch ingress. |

#### Architectural Deductions:
1. **Refutation of Heuristic Claim:** Orders traverse an exclusive egress port (`tsnSwitch -> ap`) and never share a buffer with telemetry.
2. **Localization of TSN Benefit:** Under Option 7B, the scheduling benefits of IEEE 802.1Q priority and IEEE 802.1Qbv TAS in the wired backbone manifest on the `tsnSwitch -> fms` port, protecting both DDS coordination and State reports from telemetry overflow.

---

## 5. Lookup-Table Internal Schema (NER Interface Specification)

### 5.1 Dimension Keys (Independent Variables)
* `cell` $\in \{1, 2, 3, 4, 5, 6\}$ (Categorical, non-interpolated).
* `class` $\in \{\text{orders}, \text{dds}, \text{state}, \text{telemetry}\}$ (Categorical, non-interpolated).
* `N_AMR` $\in \{5, 10, 20, 40, 80\}$ (Continuous integer; $80$ is the upper stress point, Q5).
* `lambda_tel_Mbps` $\in \{22.4, 45.0, 60.0, 74.7, 85.0, 95.0, 110.0, 149.3\}$ (Continuous real).
* `phy_rate_Mbps` $\in \{54, [12]\}$ (Categorical factor).

---

### 5.2 Main Aggregate Table Schema (`lookup_summary.csv` / `.json`)

| Column Name | Data Type | Description & Normative Definition |
| :--- | :---: | :--- |
| `cell` | Integer | Network cell identifier (1 to 6). |
| `class` | String | Traffic class name (`orders`, `dds`, `state`, `telemetry`). |
| `N_AMR` | Integer | Active AMR fleet density. |
| `lambda_tel_Mbps` | Float | Aggregate offered background telemetry load (Mbps payload). |
| `phy_rate_Mbps` | Integer | Wireless PHY rate factor (baseline 54; sensitivity levels per Q8). |
| `n_reps` | Integer | Total independent replications executed ($R \ge 10$). |
| `n_total` | Integer | Total validated packet count across all replications. |
| `p_loss` | Float | Aggregate physical drop ratio $(n_{\text{Drop\_Queue}} + n_{\text{Drop\_Retry}} + n_{\text{Drop\_Other}}) / n_{\text{total}}$. Excludes delivered-but-late packets (`Late_Arrival` $= \text{miss\_A}_D - p_{\text{loss}}$). |
| `n_Drop_Queue` | Integer | Packets dropped due to buffer overflow. |
| `n_Drop_Retry` | Integer | Packets dropped due to wireless retry limit exhaustion. |
| `n_Drop_Other` | Integer | Packets dropped due to physical errors or unmapped events. |
| `miss_A_1ms`..`miss_A_100ms` | Float | Mean deadline miss rate under Definition A for $D \in \{1, 2, 5, 10, 20, 50, 100\}\ \text{ms}$. |
| `miss_B_1ms`..`miss_B_100ms` | Float | Mean deadline miss rate under Definition B for $D \in \{1, 2, 5, 10, 20, 50, 100\}\ \text{ms}$ ($L=D$, $T = 10\ \text{ms}$). Other $T$ and the $L_c = T$ variant are computed offline from `lookup_ecdf`. |
| `ci95_miss_B` | Float | 95% Student-$t$ confidence interval half-width of $\text{Miss}_B$ across replications. |
| `lat_p50`, `lat_p90`, `lat_p95` | Float | Delay distribution percentiles in milliseconds. |
| `lat_p99` | Float | 99th percentile delay (flagged if pooled $n < 10^4$). |
| `lat_p99_9` | Float | 99.9th percentile delay (flagged if pooled $n < 10^5$). |
| `insufficient_tail_samples` | Boolean | `true` when pooled $n < 10^4$ for $p_{99}$ or $n < 10^5$ for $p_{99.9}$. |
| `schema_version` | String | Schema version tag for the twin's parser. |

---

### 5.3 Long-Format Empirical CDF Table Schema (`lookup_ecdf.csv` / `.json`)
Stores the empirical latency quantile function of **delivered** packets ($a < \infty$) for offline interpolation and tick evaluation:
$$\text{Schema: } (\text{cell},\, \text{class},\, N_{\text{AMR}},\, \lambda_{\text{tel}},\, \text{phy\_rate\_Mbps},\, \text{quantile\_level},\, \text{delay\_ms})$$
* **Quantile levels (24, fixed):** $\{0.0, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.92, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999, 1.0\}$, concentrated in the upper tail.
* Lost packets are excluded from the finite delay quantiles and recorded in `p_loss`.
* **Locked Resolution (Oct 14):** Formally adopts the 24-point quantile grid for high-fidelity Wasserstein interpolation and tail representation.

---

### 5.4 Mathematical Interpolation Rules
1. **Categorical isolation:** `cell` and `class` are never interpolated.
2. **Quantile-space (horizontal) interpolation, not CDF-space:** Averaging CDF values at fixed delays between two operating points yields a false bimodal mixture (for example 50 % of packets at $1\ \text{ms}$ and 50 % at $15\ \text{ms}$ with none in between). Interpolating quantiles at fixed levels $q$ shifts and scales the distribution instead: $Q_\alpha(q) = (1-\alpha)\,Q_0(q) + \alpha\,Q_1(q)$, which is the 1-D Wasserstein ($W_2$) geodesic between the two distributions [18, 19].
3. **Monotone PCHIP along continuous dimensions:** Along $N_{\text{AMR}}$ and $\lambda_{\text{tel}}$, apply monotone PCHIP (Fritsch & Carlson [11]) independently to each quantile level and to `p_loss`. Natural cubic splines or Lagrange polynomials can overshoot at the steep FIFO saturation knee (sub-millisecond delay jumping to the $9.408\ \text{ms}$ buffer ceiling) and produce negative or non-monotone values. *Implementation guard (added Oct 14):* after interpolation, enforce non-crossing across levels with a cumulative maximum along $q$ and clip delays to $\ge 0$.
4. **Saturation clamping:** In asymptotic saturation regions ($\lambda_{\text{tel}} > 100\ \text{Mbps}$ for FIFO; $\lambda_{\text{tel}} > 44.8\ \text{Mbps}$ for TAS telemetry), use nearest-neighbor values.
5. **No extrapolation:** Queries outside the evaluated grid are clamped to the edge value and flagged with a logged out-of-bounds warning.
6. **Optional pre-densified export:** If the maintainers prefer, `analysis/export_lookup.py` exports an interpolated fine grid so the Java engine needs only a hash-map lookup plus piecewise-linear quantile inversion, with no cubic arithmetic at runtime.

---

### 5.5 Runtime Consumption by the Java Twin (Q3)
* **Format and location:** Tidy CSV with JSON mirror. The preferred format and the resource-tree location are confirmed during the ingestion test (checklist C3).
* **Mode 2 (recommended): stochastic inverse-transform sampling.** For each message sent at simulated time $g$, draw two independent uniforms $u_{\text{loss}}, u_{\text{delay}} \sim \mathcal{U}(0,1)$ from a PRNG seeded per flow (or per agent) from the run seed. If $u_{\text{loss}} < p_{\text{loss}}$ the message is lost ($a = \infty$). Otherwise invert the quantile table at level $u_{\text{delay}}$ (binary search plus linear or PCHIP inversion) to obtain the transport delay $\tau$ and register $a = g + \tau$. This is allocation-free and independent of thread scheduling, so `SeededReplaySeed1Test` stays deterministic when 13 agents access `nerRegistry` concurrently.
* **Mode 1 (fallback): expected-value lookup** from `lookup_summary` (`p_loss`, `lat_p50`, `lat_p95`, `lat_p99`).
* **Division of responsibility:** The table encodes network transport only. The twin applies its own consumption rules afterwards ($c$, ZOH, TTL discard; §1.3.1).
* **Ingestion prototype:** Send a 1-cell, 1-$N$, 1-$\lambda$ sample (`lookup_summary` and `lookup_ecdf`) to the maintainers to validate column names and headers before the P3 export.

---

## 6. Analytical Checks & Parameter Recomputations (Oct 13, 2026)

| Mathematical Check | Analytical Value | Status | Reference / Verification Note |
| :--- | :--- | :---: | :--- |
| **802.11g ERP-OFDM Airtime** | State: 326 µs; Orders: 266 µs; Sched: 258 µs (54 Mbps) | Verified (analytic) | Verified using SHORT slot (9 µs), SIFS (10 µs), DIFS (28 µs), 20 µs preamble, and two 6 µs signal extensions (DATA and ACK) [6]. Confirmed in `docs/capacity.md`. |
| **Wireless Medium Utilization** | $N=40$: 18% (54 Mbps); $N=200$: 92% (54 Mbps) | Verified (analytic) | Collision-free lower bound matches `analysis/capacity.py`. At 54 Mbps with 40 AMRs, medium is lightly loaded. |
| **GCL Window Partitions** | $[0, 100)$, $[100, 300)$, $[300, 500)$, $[500, 1000)\ \mu\text{s}$ | Verified (analytic) | Disjoint windows totaling exactly 1000 µs. INET offsets `[0us, 900us, 700us, 500us]` correctly implement initial cycle phases. |
| **Window Frame Ceilings** | Orders: 1; DDS: 9; State: 2; Telemetry: 4 frames/cycle | Verified (analytic) | Wire frames fit within guard bands. Telemetry ceiling is exactly $4 \times 1400\ \text{B} / 1\ \text{ms} = 44.8\ \text{Mbps}$ payload. |
| **Wired Queue Drainage Limit** | $80 \times 1470\ \text{B} / 100\ \text{Mbps} = 9.408\ \text{ms}$ | Verified (analytic) | Proves wired late arrivals are physically impossible for $D = 50\ \text{ms}$ (Finding F1, §1.9). |
| **Framing Overhead** | Tagged: 70 B; Stripped: 66 B | Verified (analytic) | Tag stripping removes 4 B 802.1Q C-tag (`0x8100`). Egress window capacities are identical under both sizes. |
| **Slack Worked Example (Q1)** | $g = 3\ \text{ms}$, $L_c = D_c = 5\ \text{ms}$, $T = 10\ \text{ms}$ $\Rightarrow$ $c = \lceil 8/10 \rceil \cdot 10 = 10\ \text{ms}$, $s = 7\ \text{ms}$; $a = 9\ \text{ms}$ on time, $a = 11\ \text{ms}$ a miss | Verified (analytic) | Matches the maintainer formula (`MainSimulator.java:422-428`) and the `DeadlineSink` test matrix (checklist C7). |
| **UDP vs. TCP Framing (Q4)** | Removing $12$ to $24\ \text{B}$ saves $0.96$ to $1.92\ \mu\text{s}$ at $100\ \text{Mbps}$: $1.1$ to $2.2\,\%$ of a State frame ($85.6\ \mu\text{s}$), $0.8$ to $1.6\,\%$ of a Telemetry frame ($117.6\ \mu\text{s}$) | Verified (analytic) | TCP $20\ \text{B}$ ($32\ \text{B}$ with timestamps) vs. UDP $8\ \text{B}$. GCL ceilings for State (2) and Orders (1) are unchanged with $+24\ \text{B}$. A TCP-framed DDS frame would not fit 9 per $200\ \mu\text{s}$ window, but DDS is natively UDP and is not affected. |
| **Wired Load Bracket (Q5)** | At $N = 40$ on $100\ \text{Mbps}$: $26.9$, $81.8$, $160.2\ \text{Mbps}$ $\Rightarrow$ $\rho \approx 0.27$, $0.82$, $1.60$. At $1\ \text{Gbps}$, $81.8/1000 \approx 0.08$ | Verified (analytic) | `capacity.md` §4. The working-session figure $23.9\ \text{Mbps}$ for $N = 40$ was the $N = 5$ value. |
| **Wireless Utilization (Q5)** | $54\ \text{Mbps}$: $N = 40$ $18\,\%$, $N = 80$ $37\,\%$. $24\ \text{Mbps}$: $N = 40$ $29\,\%$. $12\ \text{Mbps}$: $N = 40$ $48\,\%$, $N = 80$ $95\,\%$ | Verified (analytic) | `capacity.md` §2 (collision-free lower bound; real saturation starts earlier). |
| **Carrier-Sense Geometry (Q5)** | AP to AMR $\le 42.43\ \text{m}$: FSPL $72.65\ \text{dB}$, $P_{\text{rx}} = -59.6\ \text{dBm}$. AMR to AMR $\le 84.85\ \text{m}$: FSPL $78.67\ \text{dB}$, $P_{\text{rx}} = -65.7\ \text{dBm}$ | Verified (analytic) | Both far above the $-85\ \text{dBm}$ receiver sensitivity (free space, $20\ \text{mW}$, $2.412\ \text{GHz}$) $\Rightarrow$ all nodes hear each other. The AMR-to-AMR case is an addition to the working-session check. |

---

## 7. Synchronization Checklist for Other Project Documents

### 1. `docs/parameters.md`
* [x] §4 Background Noise: Relabeled from "Optimistic" to "Decision (Error-free channel by scope)"; added $-95\ \text{dBm}$ as sensitivity configuration.
* [x] §4 Transmitter Power & Frequency: Adopted 20 mW (13 dBm) and 2.412 GHz Channel 1.
* [x] §6 Telemetry Process: Defined single Poisson arrival process (`exponential(${telInterval})`) with desynchronized offset `uniform(0s, ${telInterval})`.
* [x] §6 DDS Flow Matrix: Added unicast ring pattern (`station[i] -> station[(i+1)%4]`) and confirmed FMS non-subscriber role (Q7).
* [x] §8 Buffer & Framing: Added 70 B tagged vs. 66 B stripped framing note.
* [x] §9 TAS Phase Offset: Changed from "0 µs, Decision" to "Open, derive from latency chain" (checklist C6).
* [x] Updated Implementation Guide citations from §5.1 to Step 5.1.

### 2. `docs/capacity.md`
* [x] Reference to Q6 is valid (split from Q5).
* [ ] Re-run `analysis/capacity.py` with empirical INET frame exchange times after calibration (checklist C5).

### 3. `README.md`
* [x] Added Lucas de Mello Kindermann to author list (matching Project Design Proposal).

### 4. Oct 14 Q1–Q5 Synchronization
* [x] `docs/decisions.md`: §1.1, §1.2, §1.3, new §1.3.1–§1.3.2, §1.5 item 6, §1.7, §1.8, §1.9, §2, §3, §5.2–§5.5, §6, §8 updated.
* [x] `docs/parameters.md`: new §6.1 (consumption model), §6.2 (transport), §10 (lookup export).
* [x] `docs/checklist_secao3.md`: A3, E0, C1, C2, C3, C4, C7 updated.
* [x] `docs/schedule.md`: status block, Stage 0, P1 gate, C7, C3 rows, Gate 1 updated.
* [x] Implementation Guide: Steps 0.2, 0.3, 5.3 updated; new Step 9.5.
* [x] Q5: sweep $N \in \{5, 10, 20, 40, 80\}$ propagated to `parameters.md` §3, §3.1, §5; sample-size row for $N = 80$ in §1.6; `checklist_secao3.md` A3, C4; `schedule.md` P1 gate, C6, C9; Implementation Guide Step 9.2.
* [ ] `simulations/omnetpp.ini`: set the sweep `*.numAmrs = 5, 10, 20, 40, 80` and give AMR coordinates a dedicated RNG stream.
* [ ] Ask the maintainers for the canonical station and AMR counts of the twin.
* [ ] `analysis/export_lookup.py`: implement 15-level quantile export, quantile-space PCHIP with the non-crossing guard, `schema_version`, `insufficient_tail_samples`.
* [ ] `simulations/omnetpp.ini` and `DeadlineSink`: add the staleness histogram, the $D = 100\ \text{ms}$ level and the $L_c = T$ variant.
* [ ] Ask the maintainers: TTL constants (Q2), $L_c$ for State/Telemetry (§1.3.2), preferred ingestion format and resource path (Q3).

---

## 8. Normative References & Bibliographic Citations

1. **[1] 3GPP TS 22.104:** 3rd Generation Partnership Project; Technical Specification Group Services and System Aspects; *Service requirements for cyber-physical control applications in vertical domains* (Release 18), v18.4.0, Mar. 2024.
2. **[2] 5G-ACIA:** 5G Alliance for Connected Industries and Automation; *Integration of 5G with Time-Sensitive Networking for Industrial Automation*, White Paper, Nov. 2021.
3. **[3] 5G-ACIA:** 5G Alliance for Connected Industries and Automation; *5G for Automation in Industry*, White Paper, 3rd Edition, May 2021.
4. **[4] VDA and VDMA:** *VDA 5050: Interface for the Communication between Mobile Robots and a Fleet Control*, Version 3.0.0, Mar. 2026.
5. **[5] Object Management Group (OMG):** *Data Distribution Service (DDS)*, Version 1.4, Apr. 2015; and *Real-Time Publish-Subscribe Wire Protocol (DDSI-RTPS)*, Version 2.3, May 2019.
6. **[6] IEEE Std 802.1Qbv-2015:** IEEE Standard for Local and Metropolitan Area Networks—Bridges and Bridged Networks—*Amendment 25: Enhancements for Scheduled Traffic*, IEEE Computer Society, Mar. 2016.
7. **[7] RFC 768:** J. Postel, *User Datagram Protocol*, IETF RFC 768, Aug. 1980.
8. **[8] RFC 9293:** E. Eddy, Ed., *Transmission Control Protocol (TCP)*, IETF RFC 9293 (incorporating RFC 793 and RFC 5681), Aug. 2022.
9. **[9] R. Jain:** *The Art of Computer Systems Performance Analysis: Techniques for Experimental Design, Measurement, Simulation, and Modeling*, John Wiley & Sons, New York, NY, USA, 1991.
10. **[10] IEEE Std 1516-2010:** IEEE Standard for Modeling and Simulation (M&S) *High Level Architecture (HLA)—Framework and Rules*, IEEE Computer Society, Aug. 2010.
11. **[11] F. N. Fritsch and R. E. Carlson:** *Monotone Piecewise Cubic Interpolation*, SIAM Journal on Numerical Analysis, vol. 17, no. 2, pp. 238–246, Apr. 1980.
12. **[12] H. Wickham:** *Tidy Data*, Journal of Statistical Software, vol. 59, no. 10, pp. 1–23, Sep. 2014.
13. **[13] B. da Silva Pereira, G. S. Stuart, and L. de Mello Kindermann:** *Bottleneck Migration in Hybrid Wired and Wireless Industrial Networks: A Discrete-Event Simulation Study for the Matrix Factory Twin*, Project Design Proposal, Department of Informatics and Statistics (INE), UFSC, Sep. 2026.
14. **[14] 3GPP TR 38.901:** 3rd Generation Partnership Project; Technical Specification Group Radio Access Network; *Study on channel model for frequencies from 0.5 to 100 GHz* (Release 17), v17.0.0, Mar. 2022.
15. **[15] IEEE Std 802.11-2020:** IEEE Standard for Information Technology—Telecommunications and Information Exchange between Systems—Local and Metropolitan Area Networks—*Specific Requirements Part 11: Wireless LAN Medium Access Control (MAC) and Physical Layer (PHY) Specifications*, IEEE Computer Society, Feb. 2021.
16. **[16] P. Pazzaglia, C. Mandrioli, M. Maggio, and A. Cervin:** *DMAC: Deadline-Miss-Aware Control*, 31st Euromicro Conference on Real-Time Systems (ECRTS 2019), LIPIcs vol. 133, art. 1, 2019, doi: 10.4230/LIPIcs.ECRTS.2019.1. (Analyses killing a late job, skipping the next activation, and queueing, under Logical Execution Time.)
17. **[17] K. Zanbouri, M. Noor-A-Rahim, J. John, C. J. Sreenan, H. V. Poor, and D. Pesch:** *A comprehensive survey of wireless Time-Sensitive Networking (TSN): Architecture, technologies, applications, and open issues*, IEEE Communications Surveys & Tutorials, vol. 27, no. 4, pp. 2129–2155, 2025, doi: 10.1109/COMST.2024.3486618. (Also Proposal reference [7].)
18. **[18] V. M. Panaretos and Y. Zemel:** *Statistical Aspects of Wasserstein Distances*, Annual Review of Statistics and Its Application, 2019.
19. **[19] C. Villani:** *Optimal Transport: Old and New*, Springer, 2009.

> **Citations not adopted (could not be verified on Oct 14):** Gallant et al., arXiv:2608.18850; Macias-Rivera et al., *Telecom* 7(5), 124; Duan et al., *IEEE Wireless Commun. Lett.* 15, 4986–4990; the Inoue/Takine Age-of-Information book chapter and Vecchio, arXiv:2405.05849 as quoted in the working session. Verify the originals before citing them in a report.
