# Matrix Factory Twin: Simulation Parameters Sheet

This sheet catalogs every parameter in the simulation model ([simulations/omnetpp.ini](../simulations/omnetpp.ini) and [simulations/MatrixFactoryNetwork.ned](../simulations/MatrixFactoryNetwork.ned)).

**Revision:** Oct 14, 2026. All eight architectural and experimental questions (Q1–Q8) are now formally locked (see [decisions.md](decisions.md) §2).

### Parameter Status Definitions
* **Placeholder:** Unconfirmed baseline value awaiting measurement or confirmation from twin maintainers (see [decisions.md](decisions.md)).
* **Decision:** Design or modeling choice adopted in configuration, pending experimental test.
* **Verified:** Empirically verified against INET 4.7.0 execution and validation steps (Phases 3–4).
* **Confirmed (maintainer):** Confirmed by the Matrix Factory Twin maintainers against the twin's source code (Oct 14, 2026).

---

## 1. Pinned Software & Platform Environment

| Parameter | Value | Status | Reference / Notes |
| :--- | :--- | :---: | :--- |
| **Operating System** | Linux 6.1.0-52-amd64 x86_64 (Debian 12) | Decision | Base research environment |
| **C++ Compiler** | GCC 12.2.0 (`Debian 12.2.0-14+deb12u1`) | Decision | Host C++ toolchain |
| **OMNeT++ Version** | OMNeT++ 6.4.0 (`~/omnetpp-6.4.0`) | Decision | Pinned simulation kernel |
| **INET Framework** | INET 4.7.0 (`commit dfe270b21f`) | Decision | Pinned protocol framework |
| **Python Environment**| Python 3.11+ with venv (`pandas`, `scipy`, `matplotlib`) | Decision | Offline analysis tooling |

---

## 2. Simulation Execution & Environment

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **Sim Time Limit** | `sim-time-limit` | `60` | s | Verified | Working assumption (Q5); C9 | Run duration; validated in C9 pilot for statistical sample size adequacy ($n \ge 10^4$ for $p_{99}$). |
| **Warmup Period** | `warmup-period` | `5` | s | Verified | C9 Pilot Validation | Transient cutoff; validated via 338k vector queue samples (stationary at 79.27 pkts, max dev 0.04 pkts). |
| **Number of RNGs** | `num-rngs` | `3` | - | Verified | Architecture choice (C8) | `rng-0`: MAC/protocols, `rng-1`: traffic generators, `rng-2`: AMR mobility. Validated in C8. |
| **App Generator RNG** | `**.app[*].source.rng-0` | `1` | - | Verified | Architecture choice (C8) | Guarantees offered load parity across cells. Validated in C8. |
| **AMR Mobility RNG** | `*.amr[*].mobility.rng-0` | `2` | - | Verified | Architecture choice (C8) | Dedicated spatial stream; identical AMR positions in CSMA and Sched. Validated in C8. |
| **Replication Count** | `repeat` | `10` | runs | Verified | C9 Pilot Validation | Target confidence interval half-width (Jain formula) validated in C9 pilot ($R=10$). |
| **Seed Set** | `seed-set` | `${repetition}` | - | Decision | Standard OMNeT++ | Controlled pseudo-random seed variation. |
| **Vector Recording** | `**.vector-recording` | `false` | bool | Decision | Implementation Guide Step 5.1 | Disabled for campaign runs; enabled only in `[Config Debug]`. |
| **Scalar Recording** | `**.scalar-recording` | `true` | bool | Decision | Implementation Guide Step 5.1 | Summary statistics, drop counters, and packet totals. |
| **Histogram Recording**| `**.histogram-recording`| `true` | bool | Decision | Implementation Guide Step 5.1 | Captures delay/jitter distributions without vector file bloat. |

---

## 3. Network Topology & Addressing

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **AMR Fleet (Point)** | `*.numAmrs` | `10` | nodes | Decision | Q5 (approved Oct 14) | Baseline operating point for single-run debugging (`Cell1`..`Cell6`). |
| **AMR Fleet Sweep** | `*.numAmrs` | `5, 10, 20, 40, 80` | nodes | Decision | Q5 (approved Oct 14) | Fleet scaling range; $N = 80$ is the upper stress point (see §3.1 and the capacity analysis in §5). |
| **Station Count** | `*.numStations` | `4` | nodes | Decision | Q5 (approved Oct 14) | Manufacturing workstations exchanging inter-station DDS and telemetry (controlled scale model). |
| **Wired Link Bitrate** | `*.eth[*].bitrate` | `100` | Mbps | Decision | Q5 (approved Oct 14) | Fast Ethernet (100Base-TX) connecting FMS, Switch, Stations, and AP. Keeps the backbone near saturation (§3.1). |
| **IP Address Block** | `*.configurator.config` | `10.0.x.x / 16` | - | Decision | Architecture choice | Single flat L2 broadcast domain. |
| **Disjunct Subnets** | `assignDisjunctSubnetAddresses` | `false` | bool | Decision | Architecture choice | Transparent bridging across AP and TSN switch. |
| **Global ARP** | `GlobalArp` | `true` (default) | bool | Verified | INET `TsnNetworkBase` | Eliminates ARP request bursts and initial frame delays. |

---

### 3.1 Factory Scale & Geometry (Q5, approved Oct 14, 2026)

| Parameter | Value | Status | Rationale |
| :--- | :--- | :---: | :--- |
| **Fleet sweep $N$** | $\{5, 10, 20, 40, 80\}$; point mode $10$ | Decision | The twin's 13 agents lie inside the grid; no extrapolation. $N = 80$ gives $37\,\%$ wireless utilization at 54 Mbps and $95\,\%$ at 12 Mbps. |
| **Twin composition** | 13 JaCaMo agents; split into stations and AMRs not yet given | Open (non-blocking) | Ask the maintainers; any AMR count between 5 and 80 is covered. |
| **Wired offered load at $N = 40$** | $26.9$ / $81.8$ / $160.2$ Mbps for telemetry $22.4$ / $74.7$ / $149.3$ Mbps | Verified (analytic) | $\rho \approx 0.27$ / $0.82$ / $1.60$ on $100$ Mbps; at $1$ Gbps the middle point would be $\rho \approx 0.08$. |
| **Link speed rationale** | $100$ Mbps kept as a scale model | Decision | Scaling capacity relative to background load studies the queueing knee without simulating ten times more packets. |
| **AMR-to-AP / AMR-to-AMR distance** | $\le 42.43$ m / $\le 84.85$ m | Verified (analytic) | Received power $-59.6$ dBm and $-65.7$ dBm, above the $-85$ dBm sensitivity: no hidden terminals. |
| **Spatial RNG** | Dedicated stream for AMR coordinates | Decision | Same positions in `Radio_CSMA` and `Radio_Sched` for a given seed (checklist C8). |
| **Baseline grid size** | $6 \times 5 \times 3 = 90$ points (was 72); densified production grid about $2{,}400$ to $6{,}000$ runs | Decision | $6 \times 5 \times (8\text{ to }10) \times 10 \times (1\text{ to }2)$; to be costed in the pilot (checklist C9). |

---

## 4. Wireless (IEEE 802.11) Physical & MAC Parameters

| Parameter | INI / INET Default Key | Baseline / Default | Units | Status | Source / Provenance | Rationale & Notes |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **Radio Medium Model** | `radioMedium` | `Ieee80211ScalarRadioMedium` | - | Decision | INET 4.7 standard | Standard scalar packet-level radio medium. |
| **Hall Dimensions** | `constraintAreaMax[X,Y]` | `(200, 200, 0)` | m | Decision | Q5 (approved Oct 14) | 200 m &times; 200 m indoor manufacturing facility. |
| **AP Coordinates** | `*.ap.mobility.initial[X,Y]` | `(100, 100, 0)` | m | Decision | Central layout | Centrally mounted AP. |
| **AMR Mobility Model** | `*.amr[*].mobility.typename` | `StationaryMobility` | - | Decision | Proposal §1 scope | AMRs stationary during communication bursts; excludes spatial fading. |
| **AMR Coordinates** | `*.amr[*].mobility.initial[X,Y]` | `100 ± uniform(-30, 30)`| m | Decision | Layout choice; Q5 | All AMRs within 42.43 m of the AP and 84.85 m of each other (no hidden nodes). Use a dedicated RNG stream, not `rng-0` (checklist C8). |
| **AP Static MAC** | `*.ap.wlan[*].address` | `10:00:00:00:00:00` | MAC | Decision | Addressing choice | Explicit static BSSID for simplified association. |
| **AP Management Type** | `wlan[*].mgmt.typename` | `Ieee80211MgmtApSimplified`| - | Decision | INET examples | Skips IEEE 802.11 association exchange transients. |
| **STA Management Type**| `wlan[*].mgmt.typename` | `Ieee80211MgmtStaSimplified`| - | Decision | INET examples | Simplified STA management paired with AP. |
| **Management Channels**| `**.mgmt.numChannels` | `2` | - | Verified | INET requirement | Required by INET simplified 802.11 management submodule. |
| **Operation Mode** | `**.wlan[*].opMode` | `g(erp)` | - | Decision | Q5 (approved Oct 14) | IEEE 802.11g ERP-OFDM mode. |
| **Wireless Bitrate** | `**.wlan[*].bitrate` | `54` (Sweep: `54, 12`) | Mbps | Decision | Q5, Q8 (locked Oct 14) | 802.11g baseline PHY rate; 12 Mbps factor in sweep. |
| **Transmitter Power** | `transmitter.power` | `20` | mW | Decision | INET default (13 dBm) | Adopted standard 20 mW (13 dBm) transmitter power. |
| **Carrier Frequency** | `transmitter.centerFrequency` | `2.412` | GHz | Decision | INET default Channel 1 | Standard 802.11 Channel 1 (2.412 GHz). |
| **Receiver Sensitivity**| `receiver.sensitivity` | `-85` | dBm | Decision | INET `Ieee80211Radio` | Demodulation threshold for basic sensitivity. |
| **SNIR Threshold** | `receiver.snirThreshold` | `4` | dB | Decision | INET `Ieee80211Radio` | Signal-to-noise-and-interference ratio threshold. |
| **Background Noise** | `backgroundNoise.power` | `-110` | dBm | Decision | Intentional modeling choice | **Error-free channel by scope:** yields ~50.4 dB SNR at 42.4 m in free space. The $-95\ \text{dBm}$ noise floor (yielding ~35.4 dB SNR in free space, or ~24 dB in InF-NLOS) is retained as an optional sensitivity configuration. |
| **MAC Pending Queue** | `mac.dcf.channelAccess.pendingQueue.packetCapacity` | `100` | packets | Decision | INET `PendingQueue.ned` | 100 packets MAC buffer per node (vs. 20 packets/class wired). |
| **Short Retry Limit** | `mac.dcf.recoveryProcedure.shortRetryLimit` | `7` | retries | Verified | INET `NonQosRecoveryProcedure` | Standard IEEE 802.11 short retry limit. |
| **Long Retry Limit** | `mac.dcf.recoveryProcedure.longRetryLimit` | `4` | retries | Verified | INET `NonQosRecoveryProcedure` | Standard IEEE 802.11 long retry limit. |
| **RTS Threshold** | `mac.dcf.rtsPolicy.rtsThreshold` | `2346` | B | Verified | INET `RtsPolicy.ned` | Exceeds MTU (2304 B) &rarr; RTS/CTS disabled by default. |
| **Fragmentation Thresh**| `mac.fragmentationPolicy.fragmentationThreshold` | `1500` | B | Verified | INET `BasicFragmentationPolicy` | IP packets $\le 1500$ B are not fragmented. |
| **MAC Frame Aggregation**| `mac.qosStation` | `false` | bool | Verified | INET `Ieee80211Mac.ned` | A-MSDU / A-MPDU disabled for non-QoS stations. |

---

## 5. Capacity Analysis & Radio Saturation Check

Based on the analytic capacity model ([analysis/capacity.py](../analysis/capacity.py) &rarr; [docs/capacity.md](capacity.md)), the single-frame exchange times under 802.11g ERP-OFDM are:
* **State Report (1000 B payload):** ~326 µs airtime at 54 Mbps.
* **Order Dispatch (600 B payload):** ~266 µs airtime at 54 Mbps.

### Wireless Channel Utilization vs. Fleet Size (CSMA, Collision-Free Lower Bound)

| Fleet Size $N$ | 54 Mbps | 24 Mbps | 12 Mbps | 6 Mbps |
| :---: | :---: | :---: | :---: | :---: |
| **5 AMRs** | 2% | 4% | 6% | 11% |
| **10 AMRs** | 5% | 7% | 12% | 21% |
| **20 AMRs** | 9% | 14% | 24% | 43% |
| **40 AMRs** | **18%** | **29%** | **48%** | **86%** |
| **80 AMRs** | 37% | 57% | 95% | >100% |

> [!WARNING]
> **Radio Bottleneck Warning:** At 54 Mbps with 40 AMRs, the wireless medium reaches only ~18% utilization. Contention delay and backoff collisions will be minimal, meaning the "wireless bottleneck at high fleet density" hypothesis may not manifest.
> **Mitigation Options for Phase 9 Pilot:**
> 1. Lower the wireless PHY rate in sweep configurations (e.g., test 12 Mbps or 24 Mbps).
> 2. Fleet sweep extended to N = 80 (adopted in Q5): 37% at 54 Mbps and 95% at 12 Mbps. N = 120 remains optional.
> 3. Increase state report payload or transmission frequency based on real VDA 5050 captures (Q6, still open).

---

## 6. Application Traffic Classes & QoS Mapping

| Traffic Class | Direction | UDP Port | PCP | Traffic Class (TC) | Priority | Payload Size | Generation Interval | Initial Offset | Deadline ($D_c$) | Lead Time ($L_c$) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Orders** (VDA 5050) | FMS &rarr; AMR | `5051` | `6` | `TC 3` | Highest | `600` B | `exponential(200ms)` | `uniform(0s, 200ms)` | $50\ \text{ms}$ | $50\ \text{ms}$ | Decision (Q6) |
| **DDS** (Inter-station) | Station &rarr; FMS | `5100` | `4` | `TC 2` | High | `200` B | `uniform(9.5ms, 10.5ms)` *(jitter $\pm 5\%)$* | `uniform(0s, 10ms)` | $5\ \text{ms}$ | $5\ \text{ms}$ | Decision (Q7, Opt 7B) |
| **State** (VDA 5050) | AMR &rarr; FMS | `5050` | `2` | `TC 1` | Medium | `1000` B | `uniform(90ms, 110ms)`| `uniform(0s, 100ms)` | $50\ \text{ms}$ | $50\ \text{ms}$ | Decision (Q6) |
| **Telemetry** (Sensors) | Station &rarr; FMS | `5200` | `0` | `TC 0` | Background | `1400` B | `exponential(${telInterval})`<br>*(Point: 2000µs; Sweep: 8 levels)* | `uniform(0s, ${telInterval})` | $100\ \text{ms}$ | N/A (excluded) | Decision (Q8) |

*Note: Telemetry Generator Process (Q8 Locked): Poisson arrival process (`exponential(interval)`) per station across all configurations (Point and Sweep). 8-level sweep intervals (`2000, 996, 747, 600, 527, 472, 407, 300 µs`) bracket both the 44.8 Mbps TAS gate ceiling and the 100 Mbps FIFO saturation knee (aggregate payload 22.4, 45.0, 60.0, 74.7, 85.0, 95.0, 110.0, 149.3 Mbps). Initial offset scales dynamically with interval (`uniform(0s, ${telInterval})`), guaranteeing that the 4 stations are desynchronized at $t=0$ across all arrival rates.*

*Note: Deadline and lead-time columns (Q1/Q2 Locked): $D_c$ and $L_c$ are locked modeling parameters under the two-tier framework of §6.1 ($D_{\text{orders}}=50\text{ ms}$, $D_{\text{state}}=50\text{ ms}$, $D_{\text{dds}}=5\text{ ms}$, $D_{\text{tel}}=100\text{ ms}$, evaluated across $D \in \{1, 2, 5, 10, 20, 50, 100\}\text{ ms}$). Late-arrival semantics: KILL for Orders/DDS; ZOH for State/Telemetry.*

*Note: DDS Flow Matrix (Q7 Option 7B Locked): Station $i$ sends DDS coordination traffic directly to FMS on UDP port 5100 (`*.station[*].app[0].io.destAddress = "fms"`). DDS traverses the contended `tsnSwitch -> fms` egress port alongside State and Telemetry, activating priority and TAS gating discrimination.*

---

### 6.1 Application Consumption Model (Q1 / Q2, Oct 14, 2026)

| Parameter | Value | Status | Source / Rationale |
| :--- | :--- | :---: | :--- |
| **Finest simulated tick $T_{\min}$ (`MIN_DT`)** | $10$ ms ($100$ Hz) | Confirmed (maintainer) | `MainSimulator.java:56-57`. No simulated tick is shorter. |
| **Macro step (`MAX_DT`)** | $1000$ ms ($1$ Hz) | Confirmed (maintainer) | Idle step; also the electricity spot-price cadence. |
| **Active AMR step** | $50$ to $500$ ms (`soonestNeed = min(0.5, max(dwellRemaining, 0.05))`) | Confirmed (maintainer) | `AMRArtifact.java:495, 499`. $0.05$ s is the minimum active kinematic step. |
| **Quorum timeout (`TICK_QUORUM_TIMEOUT_MS`)** | $10$ ms, **wall-clock** | Confirmed (maintainer) | Thread barrier for the 13 JaCaMo agents, not simulated time; not a model parameter. |
| **Tick period used for Definition B** | Primary $T = 10$ ms; offline sensitivity $T \in \{50, 500\}$ ms | Decision | Evaluated from `lookup_ecdf` without re-running OMNeT++. |
| **Consumption instant** | $c = \lceil (g + L_c)/T \rceil \cdot T$ | Confirmed (maintainer) | `MainSimulator.java:422-428`. |
| **Boundary condition** | On time iff $a \le c$ (non-strict) | Confirmed (maintainer) | `issueTimeAdvanceGrant`: `time >= requestedNextTime`. |
| **Clock stall on late arrival** | Never | Confirmed (maintainer) | `MainSimulator.java:255-258`. |
| **Late arrival: State, Telemetry** | Zero-Order Hold; late update consumed at $c' = \lceil a/T \rceil \cdot T$ | Confirmed (maintainer) | `assembleTelemetryFrame()` (`MainSimulator.java:301-420`). |
| **Late arrival: Orders, DDS** | Consumed at first tick $\ge a$ while $a \le g + \text{TTL}$; discarded (KILL) beyond TTL | Confirmed (maintainer) | `TimerArtifact.evaluateTTLs()`, `cancelTransport`, `recordWatchdogFired`. |
| **Lead time $L_c$** | Working choice $L_c = D_c$ for all classes. Maintainer variant for State/Telemetry: $L_c = T$ (computed offline) | **Open** | decisions.md §1.3.2. Ask maintainers which reading the twin implements for State. |
| **Tier 1: network budget $D^{\text{net}}_c$** | Orders $50$ ms; State $50$ ms; DDS $5$ ms; Telemetry $100$ ms | Decision (experimental parameters) | 3GPP TS 22.104 and 5G-ACIA ranges: AGV guidance $10$ to $50$ ms; interlocking $1$ to $5$ ms; monitoring $10$ to $100$ ms. |
| **Tier 1 sensitivity markers** | State and Orders at $10$ ms and $20$ ms | Decision | Tighter operational baseline (checklist A3). |
| **Deadline spectrum $D$** | $\{1, 2, 5, 10, 20, 50, 100\}$ ms | Decision | Continuous Miss-vs-$D$ curves for Definitions A and B (decisions.md §1.7). |
| **Tier 2: twin watchdog $\text{TTL}^{\text{app}}_c$** | CNP, 2PC, `await_station_start`, `tProc`: **unknown** | **Open** | Constants requested from the maintainers; recorded separately from $D^{\text{net}}_c$. |
| **Staleness measure** | $\Delta k_{\text{stale}} = \max(0, \lceil a/T \rceil - \lceil (g + L_c)/T \rceil)$ for delivered State/Telemetry | Decision | `DeadlineSink` histogram and offline eCDF evaluation. |

### 6.2 Transport Fidelity (Q4, Oct 14, 2026)

| Parameter | Value | Status | Source / Rationale |
| :--- | :--- | :---: | :--- |
| **L4 transport, all four classes** | Open-loop UDP (`UdpSourceApp` / `UdpSinkApp`) | Decision | Keeps offered load identical across cells; avoids TCP congestion feedback, head-of-line blocking and RTO masking of drop causes. |
| **Native transport of each class** | DDS/RTPS: UDP. OPC UA PubSub (UADP): UDP. VDA 5050 State/Orders: MQTT over TCP/TLS (abstracted to UDP). | Decision | Abstraction documented as a threat to validity (decisions.md §2, Q4). |
| **L4 header difference** | UDP $8$ B vs. TCP $20$ B ($32$ B with timestamps): $12$ to $24$ B per packet | Verified (analytic) | $0.96$ to $1.92$ $\mu$s at $100$ Mbps; $1.1$ to $2.2\,\%$ of a State frame, $0.8$ to $1.6\,\%$ of a Telemetry frame. |
| **Payload size definition** | Application payload **includes** the L7 protocol header (MQTT/RTPS/UADP) | Verified | Sizes locked to VDA 5050 standard (State: 1000 B, Orders: 600 B) per Q6. |
| **Broker** | None. The FMS is the endpoint (AMR $\to$ AP $\to$ tsnSwitch $\to$ FMS). | Decision | Avoids a second switch traversal and broker-queue effects. |

---

## 7. TSN Switch Architecture & Tagging Pipeline

| Parameter | INI Key | Value | Status | Reference / Rationale |
| :--- | :--- | :--- | :---: | :--- |
| **Stream Identification** | `*.tsnSwitch.hasOutgoingStreams` | `true` | Decision | Required to classify untagged packets entering from AP or stations. |
| **Stream Classifier Mapping** | `streamIdentifier.identifier.mapping` | `orders: port 5051`<br>`dds: port 5100`<br>`state: port 5050`<br>`telemetry: port 5200` | Decision | Classifies L4 UDP streams at switch ingress. |
| **Stream Priority Encoder** | `streamCoder.encoder.mapping` | `orders &rarr; PCP 6`<br>`dds &rarr; PCP 4`<br>`state &rarr; PCP 2`<br>`telemetry &rarr; PCP 0` | Decision | 4 traffic classes mapped to IEEE 802.1Q priority code points. |
| **PCP to Queue Mapping** | INET internal classifier | `PCP (6, 4, 2, 0) &rarr; TC (3, 2, 1, 0)` | Verified | Standard INET `PcpTrafficClassClassifier` mapping for 4 queues. |
| **Tag Stripping on Egress** | `excludeEncapsulationProtocols` | `["ieee8021qctag"]` | Decision | Configured on `tsnSwitch.bridging.directionReverser` to prevent sending 802.1Q tags to untagged/radio ports. |
| **MAC Address Learner** | `interfaceRelay.learner.typename` | `RelayInterfaceLearner` | Decision | Re-enables dynamic MAC learning because AMR MACs reside behind the AP bridge. |

---

## 8. Queuing & Scheduling Disciplines (Backbone Matrix)

| Discipline | Configuration | Egress Queue Type | Queue Capacity | Transmission Gates | Total Buffer Budget | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **FIFO (Best Effort)** | `[Config Wired_FIFO]` (Cell 1, 2) | Single `DropTailQueue` | `80` packets | None (always open) | 80 packets | Decision |
| **802.1Q Strict Priority**| `[Config Wired_Prio]` (Cell 3, 4) | 4 &times; `DropTailQueue` | `20` packets / class | 4 gates, `durations=[]` (held permanently open) | 80 packets (4 &times; 20) | Decision |
| **802.1Qbv (TAS)** | `[Config Wired_TAS]` (Cell 5, 6) | 4 &times; `DropTailQueue` | `20` packets / class | 4 gates, cyclical GCL schedule (1 ms period) | 80 packets (4 &times; 20) | Decision |

> [!NOTE]
> **Buffer Parity & Frame Encapsulation Overhead:** The 80-packet budget maintains parity in *packet count*, but not *byte capacity*. `DropTailQueue` also supports `dataCapacity` (in bytes). If packet sizes differ widely between classes (200 B vs 1400 B), byte-based capacity sensitivity should be evaluated in Phase 9. On the wire, frames include 70 B of total overhead with the IEEE 802.1Q C-tag (66 B headers/preamble/FCS/gap + 4 B tag), and 66 B after tag stripping (`excludeEncapsulationProtocols = ["ieee8021qctag"]`). Egress window capacities are identical in both cases.

### 802.1Qbv Gate Control List (GCL) Window Schedule (1000 µs Cycle)

| Queue / Class | Window Offset ($s$) | Window Duration ($w$) | Active Interval | INI `durations` | INI `offset` | Frame on Wire | Max Capacity / Window |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **TC 3 (Orders)** | $0\ \mu\text{s}$ | $100\ \mu\text{s}$ | $[0, 100)\ \mu\text{s}$ | `[100us, 900us]` | `0us` | 670 B (~53.6 µs) | 1 frame/cycle |
| **TC 2 (DDS)** | $100\ \mu\text{s}$ | $200\ \mu\text{s}$ | $[100, 300)\ \mu\text{s}$ | `[200us, 800us]` | `900us` | 270 B (~21.6 µs) | 9 frames/cycle |
| **TC 1 (State)** | $300\ \mu\text{s}$ | $200\ \mu\text{s}$ | $[300, 500)\ \mu\text{s}$ | `[200us, 800us]` | `700us` | 1070 B (~85.6 µs) | 2 frames/cycle |
| **TC 0 (Telemetry)**| $500\ \mu\text{s}$ | $500\ \mu\text{s}$ | $[500, 1000)\ \mu\text{s}$ | `[500us, 500us]` | `500us` | 1470 B (~117.6 µs)| 4 frames/cycle |

---

## 9. Radio Access Disciplines & Scheduled Wireless Parameters

| Parameter | Configuration | Mode / Mechanism | Baseline Value | Status | Rationale & Target |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **CSMA/CA** | `[Config Radio_CSMA]` (Cell 1, 3, 5) | Standard IEEE 802.11 DCF | Default | Decision | Baseline contention access. |
| **Scheduled MAC Typename**| `[Config Radio_Sched]` (Cell 2, 4, 6) | `ScheduledDcf` (Spike S1) | `ScheduledDcf` | Verified | Implemented in `src/ScheduledDcf.cc`; verified with 0 collisions at $N=40$ (see `docs/results.md` §3). |
| **Slot Duration** | `slotDuration` | `400 µs` @ 54Mbps, `1000 µs` @ 12Mbps | µs | Decision | 258 µs exchange + 142 µs margin @ 54Mbps; 814 µs + 186 µs margin @ 12Mbps. |
| **Superframe Duration** | `superframeDuration` | Dynamic ($3, 5, 9, 20, 48\text{ ms}$ for $N=5..80$) | ms | Decision | Integer multiple of 1 ms TAS cycle; sized to prevent slot overruns. |
| **Contention Backoff** | `cwMin/cwMax` | `0` | slots | Decision | Zero backoff slots in scheduled mode. |
| **Phase Offset to TAS** | `cyclePhaseOffset` | Configurable (`0us` default) | µs | Decision | Gated to arrive at switch in $[300, 414.4)\ \mu\text{s}$ for zero gate wait. |

---

## 10. Lookup Table Export & NER Consumption (Q3, Oct 14, 2026)

| Parameter | Value | Status | Source / Rationale |
| :--- | :--- | :---: | :--- |
| **Tables** | `lookup_summary` (point metrics) and `lookup_ecdf` (delay quantiles), each as tidy CSV with JSON mirror | Decision | Maintainers aligned (Oct 14); decisions.md §5. |
| **Dimension keys** | `cell`, `class`, `N_AMR`, `lambda_tel_Mbps`, `phy_rate_Mbps` | Decision | Categorical: `cell`, `class`. Continuous: `N_AMR`, `lambda_tel_Mbps`. |
| **Quantile levels (24)** | $0.0, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.92, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999, 1.0$ | Decision | Conditional on delivered packets; losses are in `p_loss`. High-resolution upper tail representation. |
| **Miss columns** | `miss_A_*` and `miss_B_*` for $D \in \{1, 2, 5, 10, 20, 50, 100\}$ ms | Decision | Definition B at $T = 10$ ms, $L = D$; other $T$ and $L_c = T$ computed offline. |
| **Interpolation** | Quantile-space (horizontal) with monotone PCHIP along `N_AMR` and `lambda_tel_Mbps`; non-crossing guard; delays clipped to $\ge 0$ | Decision | Fritsch & Carlson (1980); Wasserstein geodesic. |
| **Saturation clamping** | Nearest neighbor for $\lambda_{\text{tel}} > 100$ Mbps (FIFO) and $> 44.8$ Mbps (TAS telemetry) | Decision | decisions.md §5.4. |
| **Out-of-grid queries** | No extrapolation; clamp to edge value and log a warning | Decision | decisions.md §5.4. |
| **Runtime consumption** | Mode 2: seeded inverse-transform sampling with independent $u_{\text{loss}}, u_{\text{delay}}$ per flow; Mode 1 summary lookup as fallback | Decision | Preserves `SeededReplaySeed1Test` determinism. |
| **Pre-densified fine grid** | Optional export if the maintainers prefer no cubic math in Java | Open | Ask in the ingestion test. |
| **Preferred format and resource path** | CSV vs. JSON; location in the Java resource tree | **Open** | Confirm with the 1-cell, 1-$N$, 1-$\lambda$ prototype. |
| **Tail-sample flags** | `insufficient_tail_samples` when pooled $n < 10^4$ ($p_{99}$) or $< 10^5$ ($p_{99.9}$) | Decision | decisions.md §1.6. |
