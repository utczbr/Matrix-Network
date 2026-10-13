# Matrix Factory Twin: Simulation Parameters Sheet

This sheet catalogs every parameter in the simulation model ([omnetpp.ini](file:///home/stuart/Documentos/Learn/NetWork/Matrix/simulations/omnetpp.ini) and [MatrixFactoryNetwork.ned](file:///home/stuart/Documentos/Learn/NetWork/Matrix/simulations/MatrixFactoryNetwork.ned)). Every parameter is classified as **Placeholder** (to be calibrated/confirmed against real data in P2 pilot or twin specs) or **Confirmed** (standard or architecturally decided).

---

## 1. Simulation Execution & Environment

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Sim Time Limit** | `sim-time-limit` | `60` | s | Placeholder | Implementation Guide §0.1 | Must be verified in Phase 5 / Phase 9 pilot for statistical stability. |
| **Warmup Period** | `warmup-period` | `5` | s | Placeholder | Implementation Guide §5.4 | Start-up transient elimination; to be validated via moving average plot. |
| **Number of RNGs** | `num-rngs` | `2` | - | Confirmed | Guide §4.4 | `rng-0` for protocols/MACs; `rng-1` for application traffic generators. |
| **App Generator RNG** | `**.app[*].source.rng-0` | `1` | - | Confirmed | Guide §4.4 | Ensures identical offered load across all 6 comparative cells with same seed. |
| **Replication Count** | `repeat` | `10` | runs | Placeholder | Guide §9.3 | Target confidence interval half-width (Jain formula) in pilot. |
| **Seed Set** | `seed-set` | `${repetition}` | - | Confirmed | Guide §4.4 | Controlled pseudo-random replication. |
| **Vector Recording** | `**.vector-recording` | `false` | bool | Confirmed | Guide §5.1, §5.3 | Kept false for large sweeps; enabled only in `[Config Debug]`. |
| **Scalar Recording** | `**.scalar-recording` | `true` | bool | Confirmed | Guide §5.1 | Used for summary metrics, loss, and queue counters. |
| **Histogram Recording** | `**.histogram-recording` | `true` | bool | Confirmed | Guide §5.1 | Provides delay and jitter distribution quantiles without vector file bloat. |

---

## 2. Network Topology & Addressing

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AMR Fleet Size (Point)** | `*.numAmrs` | `10` | nodes | Placeholder | Project Proposal §3.4 | Baseline operating point for single-run debugging (`Cell1`..`Cell6`). |
| **AMR Fleet Sweep** | `*.numAmrs` | `5, 10, 20, 40` | nodes | Placeholder | Guide §9.4 | Sweeps from low radio contention to heavy channel saturation. |
| **Manufacturing Stations** | `*.numStations` | `4` | nodes | Placeholder | Proposal §3.4 | Production island workstations exchanging inter-station DDS and telemetry. |
| **Wired Link Bitrate** | `*.eth[*].bitrate` | `100` | Mbps | Placeholder | Proposal §3.2 | Fast Ethernet (100Base-TX) backbone connecting FMS, Switch, Stations, and AP. |
| **IP Addressing Config** | `*.configurator.config` | `10.0.x.x / 16` | - | Confirmed | Guide §3.1 | Single flat L2 broadcast domain. |
| **Disjunct Subnets** | `assignDisjunctSubnetAddresses` | `false` | bool | Confirmed | Guide §3.1 | Allows AP and switch to function purely as transparent bridges. |
| **Global ARP** | `GlobalArp` | `true` (default) | bool | Confirmed | INET `TsnNetworkBase` | Eliminates ARP request bursts and broadcast delays from initial packets. |

---

## 3. Wireless (IEEE 802.11) & Physical Medium

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Radio Medium Model** | `radioMedium` | `Ieee80211ScalarRadioMedium` | - | Confirmed | INET 4.7 standard | Standard scalar packet-level radio medium model. |
| **Constraint Area Size** | `constraintAreaMax[X,Y]` | `(200, 200, 0)` | m | Confirmed | Guide §3.1 | 200 m x 200 m indoor manufacturing hall. |
| **AP Coordinates** | `*.ap.mobility.initial[X,Y]` | `(100, 100, 0)` | m | Confirmed | Guide §3.1 | Centrally ceiling-mounted AP. |
| **AMR Mobility** | `*.amr[*].mobility.typename` | `StationaryMobility` | - | Confirmed | Proposal §3.2 (P2 scope) | AMRs stationary during communication burst in P2; mobile in P3 if required. |
| **AMR Distribution Area** | `*.amr[*].mobility.initial[X,Y]` | `100 ± uniform(-30, 30)`| m | Confirmed | Guide §3.1 | All AMRs reside within ~60 m radius of AP (guarantees no hidden terminals). |
| **AP L2 Address** | `*.ap.wlan[*].address` | `10:00:00:00:00:00` | MAC | Confirmed | Guide §2.3 | Explicit static MAC address for simplified association. |
| **AP Management Type** | `wlan[*].mgmt.typename` | `Ieee80211MgmtApSimplified`| - | Confirmed | INET examples | Skips IEEE 802.11 authentication/association negotiation transient. |
| **STA Management Type** | `wlan[*].mgmt.typename` | `Ieee80211MgmtStaSimplified`| - | Confirmed | INET examples | Simplified STA management paired with AP. |
| **Management Channels** | `**.mgmt.numChannels` | `2` | - | Confirmed | Guide §3.2 | Required by INET simplified 802.11 management submodule. |
| **802.11 Standard / Mode** | `**.wlan[*].opMode` | `g(erp)` | - | Placeholder | Proposal §3.2 | IEEE 802.11g in 2.4 GHz industrial ISM band. |
| **Wireless Bitrate** | `**.wlan[*].bitrate` | `54` | Mbps | Placeholder | Proposal §3.2 | Peak PHY rate of 802.11g ERP-OFDM. |
| **Transmitter Power** | `transmitter.power` | `2` | mW | Placeholder | INET defaults | (~3 dBm) indoor industrial microcell coverage. |
| **Carrier Frequency** | `transmitter.centerFrequency` | `2.4` | GHz | Confirmed | 802.11g spec | Standard 2.4 GHz channel. |
| **Receiver Sensitivity** | `receiver.sensitivity` | `-85` | dBm | Confirmed | 802.11g standard | Minimum receiver sensitivity threshold. |
| **SNIR Threshold** | `receiver.snirThreshold` | `4` | dB | Confirmed | INET defaults | Signal-to-noise-and-interference ratio threshold for successful demodulation. |

---

## 4. Application Traffic Classes & QoS Mapping

| Traffic Class | Direction | UDP Port | PCP | Traffic Class (TC) | Priority | Payload Size | Generation Interval | Initial Offset | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Orders** (VDA 5050 / Task) | FMS &rarr; AMR | `5051` | `6` | `TC 3` | Highest | `600` B | `exponential(200ms)` | `uniform(0s, 200ms)` | Placeholder |
| **DDS** (Inter-station Sync) | Station &rarr; Station | `5100` | `4` | `TC 2` | High | `200` B | `10ms` (periodic) | `uniform(0s, 10ms)` | Placeholder |
| **State** (VDA 5050 Telemetry) | AMR &rarr; FMS | `5050` | `2` | `TC 1` | Medium | `1000` B | `uniform(90ms, 110ms)`| `uniform(0s, 100ms)` | Placeholder |
| **Telemetry** (Sensor stream) | Station &rarr; FMS | `5200` | `0` | `TC 0` | Best-Effort | `1400` B | `exponential(2ms)` *(Point)*<br>`2ms, 600µs, 300µs` *(Sweep)* | `0s` | Placeholder |

### Packet Naming Pattern
* `**.app[*].source.packetNameFormat = "%M-%m-%c"`: Encodes module name, app ID, and sequence count for missing packet identification at sinks.

---

## 5. TSN Switch Architecture & Tagging Pipeline

| Parameter | INI Key | Value | Status | Reference / Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Stream Identification** | `*.tsnSwitch.hasOutgoingStreams` | `true` | Confirmed | Required to classify untagged packets entering from AP or stations. |
| **Stream Classifier Mapping** | `streamIdentifier.identifier.mapping` | `orders: port 5051`<br>`dds: port 5100`<br>`state: port 5050`<br>`telemetry: port 5200` | Confirmed | Classifies L4 UDP streams at ingress. |
| **Stream Priority Encoder** | `streamCoder.encoder.mapping` | `orders &rarr; PCP 6`<br>`dds &rarr; PCP 4`<br>`state &rarr; PCP 2`<br>`telemetry &rarr; PCP 0` | Confirmed | 4 traffic classes mapped to IEEE 802.1Q priority codes. |
| **PCP to Queue Mapping** | INET internal classifier | `PCP (6, 4, 2, 0) &rarr; TC (3, 2, 1, 0)` | Confirmed | Standard INET `PcpTrafficClassClassifier` mapping for 4 queues. |
| **Tag Stripping on Egress** | `excludeEncapsulationProtocols` | `["ieee8021qctag"]` | Confirmed | Prevents sending 802.1Q tagged frames over 802.11 AP radio link. |
| **MAC Address Learner** | `interfaceRelay.learner.typename` | `RelayInterfaceLearner` | Confirmed | Re-enables dynamic MAC learning disabled by default when stream features are active. |

---

## 6. Queuing & Scheduling Disciplines (Backbone Matrix)

| Discipline | Configuration | Egress Queue Type | Queue Capacity | Transmission Gates | Total Buffer Budget |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FIFO (Best Effort)** | `[Config Wired_FIFO]` (Cell 1, 2) | Single `DropTailQueue` | `80` packets | None (always open) | 80 packets |
| **802.1Q Strict Priority**| `[Config Wired_Prio]` (Cell 3, 4) | 4 &times; `DropTailQueue` | `20` packets / class | 4 gates, `durations=[]` (held permanently open) | 80 packets (4 &times; 20) |
| **802.1Qbv (TAS)** | `[Config Wired_TAS]` (Cell 5, 6) | 4 &times; `DropTailQueue` | `20` packets / class | 4 gates, cyclical GCL schedule (1 ms period) | 80 packets (4 &times; 20) |

### 802.1Qbv Gate Control List (GCL) Window Schedule (1000 µs Cycle)

| Queue / Class | Window Offset ($s$) | Window Duration ($w$) | Active Interval | INI `durations` | INI `offset` | Frame Size on Wire | Max Capacity / Window |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC 3 (Orders)** | $0\ \mu\text{s}$ | $100\ \mu\text{s}$ | $[0, 100)\ \mu\text{s}$ | `[100us, 900us]` | `0us` | 670 B (~53.6 µs) | 1 frame/cycle |
| **TC 2 (DDS)** | $100\ \mu\text{s}$ | $200\ \mu\text{s}$ | $[100, 300)\ \mu\text{s}$ | `[200us, 800us]` | `900us` | 270 B (~21.6 µs) | 9 frames/cycle |
| **TC 1 (State)** | $300\ \mu\text{s}$ | $200\ \mu\text{s}$ | $[300, 500)\ \mu\text{s}$ | `[200us, 800us]` | `700us` | 1070 B (~85.6 µs) | 2 frames/cycle |
| **TC 0 (Telemetry)**| $500\ \mu\text{s}$ | $500\ \mu\text{s}$ | $[500, 1000)\ \mu\text{s}$ | `[500us, 500us]` | `500us` | 1470 B (~117.6 µs)| 4 frames/cycle |

*Note: INET's PeriodicGate uses `offset` to represent position in cycle at $t=0$ (`offset = cycle - window_start`).*

---

## 7. Radio Access Disciplines (Radio Matrix)

| Mode | Configuration | MAC Implementation | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **CSMA/CA** | `[Config Radio_CSMA]` (Cell 1, 3, 5) | Standard `Ieee80211Mac` + `Dcf` | Confirmed | Contention-based access with backoff and retry limits. |
| **Scheduled Access**| `[Config Radio_Sched]` (Cell 2, 4, 6) | `ScheduledDcf` (Spike S1) | **Tripwire (To be implemented in Phase 7)** | Replaces DCF with slot-coordinated conflict-free access. |
