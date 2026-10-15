# Implementation Specification: DeadlineSink (Checklist C7 & Q1/Q2 Ground Truth)

**Document Reference:** `docs/SPEC-deadline-sink.md`  
**Target Module:** `src/DeadlineSink.ned`, `src/DeadlineSink.h`, `src/DeadlineSink.cc`  
**Applies to:** FMS and Station receiver endpoints across all cells  
**Revision:** Oct 14, 2026 (Locked Specification)

---

## 1. Objective & Scope

Implement `DeadlineSink` (`src/DeadlineSink.ned`, `src/DeadlineSink.h`, `src/DeadlineSink.cc`) as a C++ subclass of `inet::queueing::PassivePacketSink` that evaluates both continuous relative deadlines (**Definition A**) and discrete variable-step/grid consumption ticks (**Definition B**) online without generating multi-gigabyte `.vec` vector files during the P3 factorial campaign.

---

## 2. Mathematical Rules Evaluated Online per Packet (Locked Q1 & Q2)

Let packet $i$ of traffic class $c \in \{\text{orders}, \text{dds}, \text{state}, \text{telemetry}\}$ be created at source application timestamp $g_i = \text{packet->getCreationTime()}$ and received at the sink at timestamp $a_i = \text{simTime()}$, yielding end-to-end transport delay $\tau_i = a_i - g_i$:

### 2.1 Warmup & Unbiased Horizon Filter (`docs/decisions.md` §1.5)

1. **Warmup Transient Filter:** Discard packet from statistical metrics if $g_i < t_{\text{warmup}}$ ($5.0\text{ s}$).
2. **Horizon Censoring Guard:** Compute nominal consumption instant:
   $$c_i(D_c, T_0) = \phi + \left\lceil \frac{g_i - \phi + D_c}{T_0} \right\rceil \cdot T_0$$
   where $T_0 = 10\text{ ms}$ (`MIN_DT`) and $\phi \sim \mathcal{U}(0, T_0)$ is drawn once per replication at `initialize()` using `rng-1`. Discard packet from statistical metrics if $c_i(D_c, T_0) > t_{\text{sim-limit}}$ ($60.0\text{ s}$) to eliminate right-censoring bias.

### 2.2 Continuous Spectrum Evaluation (Definition A across 7 Thresholds)

For each threshold $D_k \in \{1, 2, 5, 10, 20, 50, 100\}\text{ ms}$:

$$\text{Miss}_{A,i}(D_k) = \mathbb{I}(\tau_i > D_k)$$

Record scalar counter `missCount_A[k]` and histogram of delivery delays.

### 2.3 Discrete NER Grid Evaluation (Definition B across 7 Thresholds and 3 Tick Periods)

Evaluate across $T_m \in \{10\text{ ms}, 50\text{ ms}, 500\text{ ms}\}$ (`MIN_DT`, minimum active `AMRArtifact` step, and nominal cell-traversal step) with lead time $L_k = D_k$ and non-strict boundary inequality $a_i \le c_i$:

$$c_i(D_k, T_m) = \phi_m + \left\lceil \frac{g_i - \phi_m + D_k}{T_m} \right\rceil \times T_m, \qquad \text{Miss}_{B,i}(D_k, T_m) = \mathbb{I}\!\left(a_i > c_i(D_k, T_m)\right)$$

Record scalar counters `missCount_B[k][m]`.

### 2.4 Late-Arrival Semantics Tracking (`KILL` vs. `ZOH` Excess Tick Staleness)

* **For ZOH flows (`state`, `telemetry`):** When $a_i > c_i(D_c, T_m)$, the packet is not discarded by the twin's `assembleTelemetryFrame()` snapshot reader; instead, it takes effect at tick $c'_i = \phi_m + \lceil (a_i - \phi_m)/T_m \rceil \cdot T_m$. Record the discrete tick staleness counter:
  $$\Delta k_{\text{stale},i}(T_m) = \max\!\left(0,\; \left\lceil \frac{a_i - \phi_m}{T_m} \right\rceil - \left\lceil \frac{g_i - \phi_m + D_c}{T_m} \right\rceil\right)$$
  Emit histogram `stalenessTicks_Tm`.

* **For TTL-guarded control flows (`orders`, `dds`):** When $a_i > c_i(D_c, T_m)$, `TimerArtifact.evaluateTTLs()` aborts the transaction (`cancelTransport` / `recordWatchdogFired`), so the packet is counted in `n_late_discarded_ttl`.

---

## 3. Domain Delay Attribution Tags (Checklist C7)

To decompose end-to-end latency into additive domain segments:

$$\text{Delay}_{\text{e2e}} = \Delta t_{\text{radio\_mac}} + \Delta t_{\text{air}} + \Delta t_{\text{AP\_fwd}} + \Delta t_{\text{switch\_gate}} + \Delta t_{\text{switch\_queue}} + \Delta t_{\text{wire\_tx}}$$

Attach a lightweight INET `DomainTimestampTag` or read INET native tags (`QueueingTimeTag`, `PropagationTimeTag` enabled via `**.measurePacketFlow = true` or ingress timestamp hooks on `ap.eth[0]` and `tsnSwitch.eth[*]`) so `DeadlineSink::consumePacket(Packet *packet)` records scalar means and histograms for:
1. `wirelessDomainDelay`: AMR/AP generation to Ethernet egress of AP.
2. `wiredSwitchDelay`: Switch ingress to switch egress transmission start (capturing 802.1Q queuing + 802.1Qbv gate wait).
3. `wireSerializationAndPropDelay`: Remaining wire transmission time.

---

## 4. Deterministic Verification Matrix (Unit Test Vectors for `DeadlineSink`)

Before running the campaign, `DeadlineSink` must pass the deterministic test cases from `checklist_secao3.md` (C7) across uniform phase $\phi \in [0, 10\text{ ms})$:

| Test Case | Measured Delay ($\tau$) | Deadline ($D$) | Lead Time ($L$) | Tick Period ($T$) | Expected $\text{Miss}_A$ | Expected $\mathbb{E}[\text{Miss}_B]$ | Notes |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Vector 1** | $2\text{ ms}$ | $5\text{ ms}$ | $5\text{ ms}$ | $10\text{ ms}$ | $0\%$ | $0\%$ | Slack $s \in [5, 15)\text{ ms} > 2\text{ ms}$ |
| **Vector 2** | $8\text{ ms}$ | $5\text{ ms}$ | $5\text{ ms}$ | $10\text{ ms}$ | $100\%$ | $\frac{8 - 5}{10} = 30\%$ | Misses tick only when phase $\phi < 3\text{ ms}$ |
| **Vector 3** | $14\text{ ms}$ | $5\text{ ms}$ | $5\text{ ms}$ | $10\text{ ms}$ | $100\%$ | $\frac{14 - 5}{10} = 90\%$ | Misses tick in 9 out of 10 phase alignments |
| **Vector 4** | $55\text{ ms}$ | $50\text{ ms}$ | $50\text{ ms}$ | $10\text{ ms}$ | $100\%$ | $\frac{55 - 50}{10} = 50\%$ | State/Orders nominal budget overrun |
