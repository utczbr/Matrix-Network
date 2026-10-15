---
name: omnetpp-inet-verifier
description: >-
  Calibrate, verify, and audit OMNeT++ and INET discrete-event network simulations, including wireless PHY/MAC airtime calibration, RNG stream isolation, IEEE 802.1Qbv TSN gate schedules, TDMA slot timing, and packet conservation laws. Use when users build, debug, or validate OMNeT++/INET models, custom MAC/sink C++ modules, or statistical pilot runs.
---

# OMNeT++ and INET Simulation Verifier

A structured verification workflow for calibrating physical and MAC timings, enforcing RNG stream orthogonality, validating IEEE 802.1Qbv Time-Aware Shaper (TAS) schedules, and auditing strict packet conservation in OMNeT++ and INET discrete-event simulations.

## When to Use
- Bringing up a new OMNeT++ and INET network topology or custom C++ extension module
- Calibrating wireless IEEE 802.11 or wired Ethernet frame exchange durations against analytical capacity models
- Implementing or testing custom MAC coordination functions (such as TDMA or scheduled access) and custom packet sinks
- Auditing multi-cell factorial experiments for offered-load parity, spatial placement parity, and lossless packet accounting
- Running statistical pilot studies to determine warmup periods, saturation knees, and replication counts

## Steps

### 1. Calibrate Unloaded Link and Wireless Airtime
Run a single-node, unloaded baseline simulation before running multi-node sweeps.

- Measure the exact frame sequence duration from the start of the data preamble to the completion of the acknowledgment (`frameSequenceStarted` to `frameSequenceFinished`).
- Compare simulated airtime against theoretical PHY/MAC framing equations (physical preamble, SIGNAL field, OFDM symbol rounding, SIFS, ACK duration at the mandatory control bitrate, DIFS, and propagation delay).
- Require agreement within 2% before trusting channel utilization or slot sizing calculations.

### 2. Enforce Multi-Stream RNG Orthogonality
Separate pseudo-random number generator streams by functional domain in the INI configuration so protocol behavior never perturbs traffic generation or node geometry.

- Assign `rng-0` to MAC contention backoff and protocol state machines.
- Assign `rng-1` to application-layer traffic generators (`**.app[*].source.rng-0 = 1`) and replication phase offsets.
- Assign `rng-2` to node spatial placement and mobility (`*.node[*].mobility.rng-0 = 2`).
- Verify orthogonality by running different MAC/queueing configurations with the same seed and asserting that generated packet counts, timestamps, and node coordinates are bit-for-bit identical.

### 3. Use 64-Bit Fixed-Point Timing in Custom C++ Modules
Never use floating-point modulo (`std::fmod`) or `double` arithmetic to evaluate periodic slot or gate boundaries in OMNeT++ C++ extensions.

- Convert all cycle, slot, and phase durations to 64-bit integer raw ticks via `simtime_t::raw()`.
- Compute cycle-relative offsets using integer modulo:
  ```cpp
  int64_t relRaw = (now.raw() - phaseOffset.raw()) % superframeDuration.raw();
  if (relRaw < 0) relRaw += superframeDuration.raw();
  ```
- Convert computed future timestamps back via `SimTime::fromRaw(targetRaw)` before calling `scheduleAt()`.

### 4. Verify TSN Gate Control Lists (GCL) and Queue Routing
Confirm that stream classification, priority tagging, and time-aware shaping operate as intended on every contended switch egress port.

- Trace `gateState:vector` in a debug run to verify that open and closed intervals match the intended cycle period and phase offsets (`offset` in `PeriodicGate` represents the initial position within the cycle at $t = 0$).
- Account for INET's implicit guard band: a frame may only start transmission if its entire wire serialization time finishes before the gate window closes.
- Verify that 802.1Q tags (0x8100) are stripped via `excludeEncapsulationProtocols = ["ieee8021qctag"]` before frames exit toward untagged wireless access points or legacy endpoints.

### 5. Audit Packet Conservation and Warmup Stabilization
Validate statistical integrity before launching production sweeps.

- Plot moving-average queue occupancy under heavy saturation to verify that start-up transients flatten before `warmup-period`.
- Filter out packets generated before `warmup-period` ($g < t_{\text{warmup}}$).
- Apply an unbiased horizon filter based on the scheduled consumption instant ($c > t_{\text{sim\_limit}}$) rather than arrival time ($a > t_{\text{sim\_limit}}$) to avoid right-censoring slower packets.
- Assert the strict packet conservation law across every flow and run:
  $$n_{\text{valid\_total}} == n_{\text{valid\_delivered}} + n_{\text{Drop\_Queue}} + n_{\text{Drop\_Retry}} + n_{\text{Drop\_Other}}$$
  and at each sink:
  $$n_{\text{received\_total}} == n_{\text{valid\_delivered}} + n_{\text{filtered\_warmup}} + n_{\text{filtered\_horizon}}$$

## Gotchas
- **Floating-point modulo drift at slot boundaries:** In IEEE 754 arithmetic, expressions like `std::fmod(0.1, 0.02)` can evaluate to `0.01999999999999998` instead of `0.0`, causing a TDMA MAC to misclassify the start of slot 0 as the end of the cycle and defer transmission for an entire superframe. Always use `simtime_t::raw()`.
- **Sub-queue drop counter paths in TSN switches:** A single FIFO port records buffer overflows on `macLayer.queue`, whereas an 802.1Q priority or 802.1Qbv TAS shaper records overflows across per-traffic-class sub-queues (`macLayer.queue.queue[0..numTrafficClasses-1]`). Querying only the top-level queue path in TAS or priority configurations will falsely report zero drops.
- **Ceiling division with integer raw ticks:** In C++, standard integer division `/` truncates toward zero. When computing ceiling tick instants `(gRaw - phiRaw + leadRaw) / tickRaw`, explicitly add 1 to the quotient when the remainder is strictly positive.
