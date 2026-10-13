# Matrix Factory Twin: Simulation Parameters Sheet

This sheet catalogs every parameter in the simulation model ([simulations/omnetpp.ini](../simulations/omnetpp.ini) and [simulations/MatrixFactoryNetwork.ned](../simulations/MatrixFactoryNetwork.ned)).

### Parameter Status Definitions
* **Placeholder:** Unconfirmed baseline value awaiting measurement or confirmation from twin maintainers (see [decisions.md](decisions.md)).
* **Decision:** Design or modeling choice adopted in configuration, pending experimental test.
* **Verified:** Empirically verified against INET 4.7.0 execution and validation steps (Phases 3–4).

---

## 1. Pinned Software & Platform Environment

| Parameter | Value | Status | Reference / Notes |
| :--- | :--- | :---: | :--- |
| **Operating System** | Linux 6.1.0-52-amd64 x86_64 (Debian 12) | Decision | Base research environment |
| **C++ Compiler** | GCC 12.2.0 (`Debian 12.2.0-14+deb12u1`) | Decision | Host C++ toolchain |
| **OMNeT++ Version** | OMNeT++ 6.4.0 (`/home/stuart/omnetpp-6.4.0`) | Decision | Pinned simulation kernel |
| **INET Framework** | INET 4.7.0 (`commit dfe270b21f`) | Decision | Pinned protocol framework |
| **Python Environment**| Python 3.11+ with venv (`pandas`, `scipy`, `matplotlib`) | Decision | Offline analysis tooling |

---

## 2. Simulation Execution & Environment

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **Sim Time Limit** | `sim-time-limit` | `60` | s | Placeholder | Working assumption (Q5) | Run duration; calibrate in Phase 9 pilot for statistical stability. |
| **Warmup Period** | `warmup-period` | `5` | s | Placeholder | Working assumption | Transient cutoff; to be validated via moving average delay plot. |
| **Number of RNGs** | `num-rngs` | `2` | - | Decision | Architecture choice | `rng-0`: MAC/protocols, `rng-1`: traffic generators. |
| **App Generator RNG** | `**.app[*].source.rng-0` | `1` | - | Decision | Architecture choice | Intended to guarantee offered load parity across cells; test in Step 4.4. |
| **Replication Count** | `repeat` | `10` | runs | Placeholder | Pilot target | Target confidence interval half-width (Jain formula) in Phase 9. |
| **Seed Set** | `seed-set` | `${repetition}` | - | Decision | Standard OMNeT++ | Controlled pseudo-random seed variation. |
| **Vector Recording** | `**.vector-recording` | `false` | bool | Decision | Implementation Guide §5.1 | Disabled for campaign runs; enabled only in `[Config Debug]`. |
| **Scalar Recording** | `**.scalar-recording` | `true` | bool | Decision | Implementation Guide §5.1 | Summary statistics, drop counters, and packet totals. |
| **Histogram Recording**| `**.histogram-recording`| `true` | bool | Decision | Implementation Guide §5.1 | Captures delay/jitter distributions without vector file bloat. |

---

## 3. Network Topology & Addressing

| Parameter | INI / NED Key | Baseline Value | Units | Status | Source / Reference | Rationale & Notes |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **AMR Fleet (Point)** | `*.numAmrs` | `10` | nodes | Placeholder | Working assumption (Q5) | Baseline operating point for single-run debugging (`Cell1`..`Cell6`). |
| **AMR Fleet Sweep** | `*.numAmrs` | `5, 10, 20, 40` | nodes | Placeholder | Working assumption (Q5) | Fleet scaling range. *Note: See capacity analysis below.* |
| **Station Count** | `*.numStations` | `4` | nodes | Placeholder | Working assumption (Q5) | Manufacturing workstations exchanging inter-station DDS and telemetry. |
| **Wired Link Bitrate** | `*.eth[*].bitrate` | `100` | Mbps | Placeholder | Working assumption (Q5) | Fast Ethernet (100Base-TX) connecting FMS, Switch, Stations, and AP. |
| **IP Address Block** | `*.configurator.config` | `10.0.x.x / 16` | - | Decision | Architecture choice | Single flat L2 broadcast domain. |
| **Disjunct Subnets** | `assignDisjunctSubnetAddresses` | `false` | bool | Decision | Architecture choice | Transparent bridging across AP and TSN switch. |
| **Global ARP** | `GlobalArp` | `true` (default) | bool | Verified | INET `TsnNetworkBase` | Eliminates ARP request bursts and initial frame delays. |

---

## 4. Wireless (IEEE 802.11) Physical & MAC Parameters

| Parameter | INI / INET Default Key | Baseline / Default | Units | Status | Source / Provenance | Rationale & Notes |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **Radio Medium Model** | `radioMedium` | `Ieee80211ScalarRadioMedium` | - | Decision | INET 4.7 standard | Standard scalar packet-level radio medium. |
| **Hall Dimensions** | `constraintAreaMax[X,Y]` | `(200, 200, 0)` | m | Placeholder | Working assumption | 200 m &times; 200 m indoor manufacturing facility. |
| **AP Coordinates** | `*.ap.mobility.initial[X,Y]` | `(100, 100, 0)` | m | Decision | Central layout | Centrally mounted AP. |
| **AMR Mobility Model** | `*.amr[*].mobility.typename` | `StationaryMobility` | - | Decision | Proposal §1 scope | AMRs stationary during communication bursts; excludes spatial fading. |
| **AMR Coordinates** | `*.amr[*].mobility.initial[X,Y]` | `100 ± uniform(-30, 30)`| m | Decision | Layout choice | All AMRs within ~42 m max distance from AP (no hidden nodes). |
| **AP Static MAC** | `*.ap.wlan[*].address` | `10:00:00:00:00:00` | MAC | Decision | Addressing choice | Explicit static BSSID for simplified association. |
| **AP Management Type** | `wlan[*].mgmt.typename` | `Ieee80211MgmtApSimplified`| - | Decision | INET examples | Skips IEEE 802.11 association exchange transients. |
| **STA Management Type**| `wlan[*].mgmt.typename` | `Ieee80211MgmtStaSimplified`| - | Decision | INET examples | Simplified STA management paired with AP. |
| **Management Channels**| `**.mgmt.numChannels` | `2` | - | Verified | INET requirement | Required by INET simplified 802.11 management submodule. |
| **Operation Mode** | `**.wlan[*].opMode` | `g(erp)` | - | Placeholder | Working assumption (Q5) | IEEE 802.11g ERP-OFDM mode. |
| **Wireless Bitrate** | `**.wlan[*].bitrate` | `54` | Mbps | Placeholder | Working assumption (Q5) | Peak 802.11g PHY rate (see capacity analysis). |
| **Transmitter Power** | `transmitter.power` | `2` mW *(INI override)*<br>`20` mW *(INET default)* | mW | Placeholder | INET `lan80211` vs default | INI overrides to 2 mW; INET default is 20 mW (13 dBm). Recommend INET default. |
| **Carrier Frequency** | `transmitter.centerFrequency` | `2.4` GHz *(INI override)*<br>`2.412` GHz *(INET default)*| Hz | Placeholder | INET `Ieee80211Radio` | Standard Channel 1 (2.412 GHz). |
| **Receiver Sensitivity**| `receiver.sensitivity` | `-85` | dBm | Decision | INET `Ieee80211Radio` | Demodulation threshold for basic sensitivity. |
| **SNIR Threshold** | `receiver.snirThreshold` | `4` | dB | Decision | INET `Ieee80211Radio` | Signal-to-noise-and-interference ratio threshold. |
| **Background Noise** | `backgroundNoise.power` | `-110` | dBm | Decision | INET default (`RadioMedium`) | **Optimistic:** yields ~40 dB SNR at 42 m (error-free channel). Realistic industrial floor is ~-95 dBm. Verify frame errors. |
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
> 2. Expand fleet sweep up to 80–120 AMRs.
> 3. Increase state report payload or transmission frequency based on real VDA 5050 captures (Q5).

---

## 6. Application Traffic Classes & QoS Mapping

| Traffic Class | Direction | UDP Port | PCP | Traffic Class (TC) | Priority | Payload Size | Generation Interval | Initial Offset | Deadline ($D_c$) | Lead Time ($L_c$) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Orders** (VDA 5050) | FMS &rarr; AMR | `5051` | `6` | `TC 3` | Highest | `600` B | `exponential(200ms)` | `uniform(0s, 200ms)` | $50\ \text{ms}$ | $50\ \text{ms}$ | Placeholder |
| **DDS** (Inter-station) | Station &rarr; Station | `5100` | `4` | `TC 2` | High | `200` B | `10ms` *(jitter $\pm 5\%$)* | `uniform(0s, 10ms)` | $5\ \text{ms}$ | $5\ \text{ms}$ | Placeholder |
| **State** (VDA 5050) | AMR &rarr; FMS | `5050` | `2` | `TC 1` | Medium | `1000` B | `uniform(90ms, 110ms)`| `uniform(0s, 100ms)` | $50\ \text{ms}$ | $50\ \text{ms}$ | Placeholder |
| **Telemetry** (Sensors) | Station &rarr; FMS | `5200` | `0` | `TC 0` | Background | `1400` B | `exponential(2ms)` *(Point)*<br>`2ms, 600µs, 300µs` *(Sweep)* | `uniform(0s, 2ms)` *(Fix)* | $100\ \text{ms}$ | N/A (excluded) | Placeholder |

*Note: Telemetry initial offset was missing in initial INI (causing artificial $t=0$ burst across all 4 stations). Recommended fix: `uniform(0s, 2ms)`.*

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
> **Buffer Parity Caveat:** The 80-packet budget maintains parity in *packet count*, but not *byte capacity*. `DropTailQueue` also supports `dataCapacity` (in bytes). If packet sizes differ widely between classes (200 B vs 1400 B), byte-based capacity sensitivity should be evaluated in Phase 9.

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
| **Scheduled MAC Typename**| `[Config Radio_Sched]` (Cell 2, 4, 6) | `ScheduledDcf` (Spike S1) | `SCHEDULED_MAC_NOT_IMPLEMENTED` | **Tripwire** | Fail-fast until Spike S1 is implemented. |
| **Slot Duration** | `*.wlan[*].mac.dcf.slotDuration` | TBD (~400 µs) | µs | Placeholder | Must fit largest state frame exchange (326 µs) + guard band. |
| **Scheduled Cycle Period** | `*.wlan[*].mac.dcf.cycleDuration` | TBD (integer multiple of 1 ms) | ms | Decision | Must align as integer multiple or divisor of the 1 ms TAS cycle. |
| **Contention Backoff** | `*.wlan[*].mac.dcf.channelAccess.cwMin/cwMax` | `0` | slots | Decision | Zero backoff slots in scheduled mode. |
| **Phase Offset to TAS** | Scheduled-to-TAS phase | `0` µs | µs | Decision | Phase alignment between wireless slot cycle and switch GCL. |
