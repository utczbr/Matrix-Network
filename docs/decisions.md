# Matrix Factory Twin: Architectural Decisions & Questions Log

This document records key modeling decisions, mathematical definitions, architectural rationales, and the formal questions submitted to course supervisors and digital twin maintainers.

---

## 1. Primary Evaluation Metric: Deadline Miss Formulations

Let:
* $g$: Packet generation/creation timestamp at the producer app.
* $a$: Packet arrival timestamp at the consumer app ($a = \infty$ if the packet is dropped or lost).
* $T$: Digital twin discrete-event simulation tick period.
* $D$: Relative application deadline per traffic class.
* $L$: Minimum processing lead-time before the consumption tick.

### Definition A: Relative Deadline (Continuous Time)
A packet experiences a deadline miss if:
$$\text{Miss}_A = \begin{cases} 1 & \text{if packet is lost or } (a - g) > D \\ 0 & \text{otherwise} \end{cases}$$

* **Characteristics:** Standard real-time networking metric. Depends solely on end-to-end lifetime $(a - g)$ and can be computed directly from delay distribution histograms.

### Definition B: Tick Grid Consumption Instant (Discrete-Event Digital Twin)
In the Matrix Factory Twin, the Next Event Request (NER) engine advances in discrete ticks of length $T$. An event generated at time $g$ with required lead time $L$ is scheduled for consumption at the discrete instant:
$$c = \left\lceil \frac{g + L}{T} \right\rceil \times T$$

A packet experiences a deadline miss if:
$$\text{Miss}_B = \begin{cases} 1 & \text{if packet is lost or } a > c \\ 0 & \text{otherwise} \end{cases}$$

### Decision & Rationale:
* **Primary Metric Selected: Definition B (with Definition A retained as continuous baseline).**
* **Implication for Simulation Instrumentation:** Definition B depends explicitly on the phase of generation $g$ relative to tick boundaries. Therefore, aggregate delay histograms alone are insufficient for campaign analysis. Per-packet tuple logging $(g, a, \text{class})$ in Python (Stage 1) or an online custom C++ `DeadlineSink` (Stage 2) is required.

---

## 2. Key Questions for Supervisors & Digital Twin Maintainers

The following questions have been formalized for Professor Antônio Augusto Medeiros Fröhlich and the Matrix Factory Twin team. Default working assumptions are logged to ensure development is never blocked.

### Question 1: Tick Period $T$ and Consumption Rule
* **Question:** What is the discrete tick period $T$ of the Matrix Factory Twin's NER engine, and what is the exact formula/lead-time for event consumption?
* **Working Assumption:** $T = 10\ \text{ms}$, minimum lead time $L = 0\ \text{ms}$ ($c = \lceil g / T \rceil \times T$).

### Question 2: Traffic Class Deadlines ($D$)
* **Question:** What is the specific real-time deadline requirement per traffic class?
* **Working Assumptions:**
  * **Orders (VDA 5050 Task):** $D = 50\ \text{ms}$
  * **DDS (Inter-station Sync):** $D = 5\ \text{ms}$
  * **State (VDA 5050 AMR State):** $D = 50\ \text{ms}$
  * **Telemetry (Sensor stream):** $D = 100\ \text{ms}$ (best-effort, loss-tolerant)

### Question 3: NER Engine Lookup Table Format & Interpolation
* **Question:** In what format, schema, and language will the NER engine ingest the network lookup tables (e.g., CSV, JSON, HDF5, C++ header)? Does the engine interpolate between grid points or use nearest-neighbor lookups?
* **Working Assumption:** Structured CSV and JSON tabular formats with multidimensional parameter indexing `(cell, nAmr, telemetryRate) -> (missRate, p50_delay, p99_delay, lossRate)`.

### Question 4: L4 Protocol Fidelity (UDP vs. TCP/MQTT)
* **Question:** Is UDP acceptable for VDA 5050 and MQTT state/orders in Phase 2, or must full TCP/TLS connection handshakes be simulated?
* **Working Assumption:** UDP with payload abstraction is used for Phase 2 to isolate queueing, TSN gating, and channel contention from TCP congestion control dynamics.

### Question 5: Physical Facility Parameters & Scale
* **Question:** What are the physical dimensions, AMR fleet bounds, station counts, and backbone link speeds in the target laboratory or industrial deployment?
* **Working Assumption:** 4 production stations, AMR fleet sweep from 5 to 40 robots, 100 Mbps Fast Ethernet backbone, 54 Mbps 802.11g wireless cell.

---

## 3. Core Architectural Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| **Switch Placement** | `TsnSwitch` sits behind `AccessPoint` (`amr <-> ap <-> tsnSwitch <-> fms/stations`) | INET's `AccessPoint` model has a standard Ethernet interface without Time-Aware Shaper (TAS) support. Placing the TSN switch behind the AP allows measuring wireless-to-wired gate-admission delay at switch egress. |
| **L2 Addressing** | Flat L2 domain with `GlobalArp` enabled | Transparent bridging without ARP request storms or routing overhead. |
| **Offered Load Parity** | `rng-0` (protocols) vs `rng-1` (traffic generators) | Guarantees that across all 6 comparative cells with identical seeds, the exact same sequence of packets and arrival times is offered. |
| **Buffer Sizing Fairness**| Total capacity = 80 packets across all wired configs | FIFO uses a single 80-packet queue; Priority and TAS use 4 &times; 20-packet queues, maintaining identical total buffer budget. |
| **802.1Q Tag Stripping** | Exclude `ieee8021qctag` on AP egress | Wireless 802.11 frames must not contain 802.1Q tags (0x8100) which would violate standard 802.11 MAC framing. |
