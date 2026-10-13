# Matrix Factory Twin: Architectural Decisions & Questions Log

This document records key modeling decisions, mathematical definitions, architectural rationales, and the formal questions submitted to course supervisors and digital twin maintainers.

---

## 1. Primary Evaluation Metric: Deadline Miss Formulations

Let:
* $g$: Packet generation/creation timestamp at the producer application.
* $a$: Packet arrival timestamp at the consumer application ($a = \infty$ if the packet is dropped or lost).
* $T$: Digital twin discrete-event simulation tick period (nominal: $10\ \text{ms}$).
* $D_c$: Application deadline for traffic class $c$.
* $L_c$: Processing lead time for traffic class $c$.

---

### Definition A: Relative Deadline (Continuous Time Baseline)
A packet of class $c$ experiences a deadline miss if it is lost or its end-to-end delay exceeds $D_c$:
$$\text{Miss}_A = \begin{cases} 1 & \text{if packet is lost or } (a - g) > D_c \\ 0 & \text{otherwise} \end{cases}$$

* **Characteristics:** Standard real-time networking metric. It depends solely on packet lifetime $(a - g)$ and can be reconstructed directly from delay histograms.

---

### Definition B: Tick Grid Consumption Instant (Digital Twin Event Consumption)
In the Matrix Factory Twin, the Next Event Request (NER) engine advances in discrete ticks of period $T$. An event generated at time $g$ requiring lead time $L_c$ is scheduled for consumption at discrete tick instant $c$:
$$c = \left\lceil \frac{g + L_c}{T} \right\rceil \times T$$

A packet experiences a deadline miss if it is lost or arrives after consumption instant $c$:
$$\text{Miss}_B = \begin{cases} 1 & \text{if packet is lost or } a > c \\ 0 & \text{otherwise} \end{cases}$$

### Critical Pitfall of Definition B with $L = 0$
If $L_c = 0$ and generation timestamp $g$ is uniformly distributed within a tick of length $T$, the probability of missing the tick is:
$$P(\text{miss}) = \frac{1}{T} \int_{0}^{T} P(\text{delay} > x) \, dx = \frac{\mathbb{E}[\text{delay}]}{T} \quad (\text{for delays } < T)$$

* **Consequence:** With $L = 0$ and $T = 10\ \text{ms}$, a constant deterministic delay of $2\ \text{ms}$ produces a $20\%$ miss rate across every cell, purely because packets generated in the final $2\ \text{ms}$ of each tick miss that tick. This collapses the metric to mean delay divided by $10\ \text{ms}$, completely masking jitter improvements delivered by TSN and scheduled access.
* **Adopted Solution:**
  1. Define class-dependent lead time $L_c = D_c$ (or $L_c = T - D_c$ based on maintainer guidance). When $L_c = D_c$, a packet misses only when its transmission delay exceeds the deadline budget within the tick boundary.
  2. Maintain Definition A as a continuous baseline in all offline reports to isolate queueing jitter from tick-phase quantization.

---

### Counting Rules & Boundary Conditions
To prevent simulation edge artifacts and in-flight distortion:
1. **Warmup Filtering:** Discard all packets generated before the warmup period ($g < t_{\text{warmup}}$).
2. **Horizon Filtering:** Discard all packets whose consumption instant falls after simulation limit ($c > t_{\text{sim-limit}}$).
3. **Causal Attribution:** For every missed packet, categorize the root cause into mutually exclusive bins:
   * `Drop_Queue`: Dropped due to switch/node buffer overflow (`packetDropQueueOverflow`).
   * `Drop_Retry`: Dropped due to 802.11 retry limit reached (`packetDropRetryLimitReached`).
   * `Late_Arrival`: Arrived at receiver, but $a > c$ (or $a - g > D_c$).
4. **Wilson Score Confidence Intervals:** When deadline misses are rare events ($N \cdot p < 5$), standard normal approximation intervals fail. Report raw event counts $(k_{\text{miss}}, n_{\text{total}})$ and compute Wilson score binomial confidence intervals.
5. **Telemetry Exclusion:** Station telemetry is background sensor traffic throttled by design in TAS cells. Telemetry is excluded from the primary deadline miss metric and reported in a separate secondary throughput/loss panel.

---

### DDS Resonance Mitigation
Station DDS sync has a nominal generation period of $10\ \text{ms}$, identical to $T = 10\ \text{ms}$. With a fixed period, each station's generation phase relative to the tick boundary is static throughout the entire run, creating an all-or-nothing artifact.
* **Resolution:** In Phase 3 sweeps, jitter the DDS period by $\pm 5\%$ (`uniform(9.5ms, 10.5ms)`) or randomize the initial tick grid phase offset $\phi \sim \text{uniform}(0, T)$ across replications.

---

## 2. Key Questions for Supervisors & Digital Twin Maintainers

| Q# | Topic | Question Details | Date Sent | Addressee | Status / Answer | Date Adopted | Working Assumption |
| :---: | :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| **Q1** | **Tick Period & Rule** | What is tick period $T$ of the NER engine, and what is the exact formula/lead time for event consumption? | Oct 13, 2026 | Prof. Antônio / Twin Maintainers | Pending | Oct 12, 2026 | $T = 10\ \text{ms}$; lead time $L_c = D_c$. |
| **Q2** | **Class Deadlines** | What are the application deadline requirements $D_c$ for each traffic class? | Oct 13, 2026 | Prof. Antônio / Twin Maintainers | Pending | Oct 12, 2026 | Orders: $50\ \text{ms}$; State: $50\ \text{ms}$; DDS: $5\ \text{ms}$; Telemetry: $100\ \text{ms}$. |
| **Q3** | **Lookup Table Format** | In what schema/format will the NER engine consume the network lookup tables (CSV, JSON, HDF5)? Does it interpolate grid points? | Oct 13, 2026 | Twin Maintainers | Pending | Oct 12, 2026 | Multidimensional JSON/CSV lookup indexed by $(cell, N, \lambda_{\text{tel}})$. Nearest-neighbor or linear interpolation. |
| **Q4** | **L4 Fidelity** | Is UDP abstraction acceptable for VDA 5050 and MQTT state/orders in Phase 2? | Oct 13, 2026 | Prof. Antônio | Pending | Oct 12, 2026 | UDP payload abstraction is used in P2 to decouple queueing/channel contention from TCP flow control. |
| **Q5** | **Factory Scale & Profiles** | What are the real AMR fleet bounds, station counts, link speeds, and actual VDA 5050 message sizes in the factory? | Oct 13, 2026 | Prof. Antônio | Pending | Oct 12, 2026 | 4 stations, 100 Mbps backbone, 802.11g wireless, fleet sweep 5–40 AMRs (evaluated against capacity model). |

---

## 3. Core Architectural Decisions

| Decision | Choice | Status | Rationale |
| :--- | :--- | :---: | :--- |
| **Switch Placement** | `TsnSwitch` sits behind `AccessPoint` (`amr <-> ap <-> tsnSwitch <-> fms/stations`) | Decision | INET's `AccessPoint` lacks TAS egress queues. Placing the switch behind the AP produces measurable gate-admission delay on uplink traffic entering the wired backbone. |
| **L2 Addressing** | Flat L2 domain with `GlobalArp` enabled | Decision | Prevents ARP broadcasts from skewing initial frame latencies. |
| **Offered Load Parity** | `rng-0` (protocols) vs `rng-1` (generators) | Decision | Intended to guarantee identical offered load across all 6 cells for a given seed; must be verified via Step 4.4. |
| **Buffer Sizing Budget**| Total 80 packets across all wired configs | Decision | FIFO has 1 $\times$ 80 queue; Priority and TAS have 4 $\times$ 20 queues. Note: parity is in packet count, not total byte capacity (`dataCapacity`). |
| **802.1Q Tag Stripping** | `excludeEncapsulationProtocols = ["ieee8021qctag"]` on `tsnSwitch` egress | Decision | Prevents transmitting 802.1Q tagged frames (0x8100) toward the AP or untagged endpoints. Applied to switch egress, not AP. |
| **MAC Learning** | `RelayInterfaceLearner` on `tsnSwitch` | Decision | Re-enables dynamic MAC learning because AMR MAC addresses reside behind the AP bridge and cannot be configured statically. |
| **Stationary AMRs** | `StationaryMobility` in manufacturing hall | Decision | Aligned with proposal §1 scope (focus on hybrid bottleneck migration without spatial fading transients). |
