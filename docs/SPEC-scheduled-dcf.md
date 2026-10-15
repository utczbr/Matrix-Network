# Implementation Specification: ScheduledDcf (Spike S1 / Checklist C6)

**Document Reference:** `docs/SPEC-scheduled-dcf.md`  
**Target Module:** `src/ScheduledDcf.ned`, `src/ScheduledDcf.h`, `src/ScheduledDcf.cc`  
**Applies to:** Cells 2, 4, 6 (`[Config Radio_Sched]`)  
**Revision:** Oct 15, 2026 (Verified & Locked Specification)

---

## 1. Objective & Scope

Implement `ScheduledDcf` in C++/NED as a drop-in subclass of `inet::ieee80211::Dcf` (`module ScheduledDcf extends Dcf`) for Cells 2, 4, and 6 (`[Config Radio_Sched]`). The module enforces conflict-free Time-Division Multiple Access (TDMA) slot gating while preserving identical IEEE 802.11g ERP-OFDM framing, physical preamble ($20\ \mu\text{s}$), SIFS ($10\ \mu\text{s}$), ACK exchange, and signal extensions ($2 \times 6\ \mu\text{s}$) as `[Config Radio_CSMA]`.

---

## 2. Dynamic Superframe Parameterization ($N \in \{5, 10, 20, 40, 80\}$ & PHY $\in \{54, 12\}\text{ Mbps}$)

In accordance with `docs/capacity.md` §1 and `docs/results.md` §1, a single exchange with $\text{CW} = 0$ takes $258.13\ \mu\text{s}$ (State, $1000\text{ B}$, including DIFS) at $54\text{ Mbps}$ and $814.13\ \mu\text{s}$ at $12\text{ Mbps}$. To prevent slot-boundary overruns and maintain synchronization with the $1\text{ ms}$ wired TAS GCL cycle, `slotDuration` is set to **$400\ \mu\text{s}$ at $54\text{ Mbps}$** (`requiredExchangeTime = 260us`) and **$1000\ \mu\text{s}$ ($1.0\text{ ms}$) at $12\text{ Mbps}$** (`requiredExchangeTime = 820us`):

| Fleet Size $N$ | AMR Uplink Slots | AP Downlink Slots | Total Slots ($S_{\text{total}}$) | $T_{\text{super}}$ @ 54 Mbps ($400\ \mu\text{s}$/slot, padded to $1\text{ ms}$) | $T_{\text{super}}$ @ 12 Mbps ($1000\ \mu\text{s}$/slot) | Mean State Slot Wait @ 54 Mbps | Max State Wait @ 54 Mbps |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **5** | 5 | 1 | 6 | $3.0\text{ ms}$ ($7\text{ slots}$) | $6.0\text{ ms}$ | $1.5\text{ ms}$ | $3.0\text{ ms}$ |
| **10** | 10 | 1 | 11 | $5.0\text{ ms}$ ($12\text{ slots}$) | $11.0\text{ ms}$ | $2.5\text{ ms}$ | $5.0\text{ ms}$ |
| **20** | 20 | 2 | 22 | $9.0\text{ ms}$ ($22\text{ slots}$) | $22.0\text{ ms}$ | $4.5\text{ ms}$ | $9.0\text{ ms}$ |
| **40** | 40 | 8 | 48 | $20.0\text{ ms}$ ($50\text{ slots}$) | $48.0\text{ ms}$ | $10.0\text{ ms}$ | $20.0\text{ ms}$ |
| **80** | 80 | 39 | 119 | $48.0\text{ ms}$ ($120\text{ slots}$) | $119.0\text{ ms}$ | $24.0\text{ ms}$ | $48.0\text{ ms}$ |

---

## 3. Wireless-to-Wired TAS Phase Alignment Law (Checklist C6)

For an AMR uplink `State` frame ($1070\text{ B}$ tagged on the wire, serialization time $t_{\text{wire\_tx}} = 85.6\ \mu\text{s}$ at $100\text{ Mbps}$) to pass through the `tsnSwitch -> fms` `TC 1` gate window $[300, 500)\ \mu\text{s}$ with **zero gate-waiting delay**, the frame must arrive completely at the switch egress queue before the implicit guard band cutoff $500\ \mu\text{s} - 85.6\ \mu\text{s} = 414.4\ \mu\text{s}$:

$$t_{\text{switch\_arrival}} = \left(t_{\text{slot\_start}} + \phi_{\text{sched}} + t_{\text{air\_data}} + t_{\text{AP\_bridge}} + t_{\text{wire\_AP\_to\_SW}}\right) \bmod 1000\ \mu\text{s} \in [300,\, 414.4)\ \mu\text{s}$$

---

## 4. C++ Class & 64-Bit Fixed-Point State Machine (`src/ScheduledDcf.ned` / `.h` / `.cc`)

### 4.1 NED Declaration (`src/ScheduledDcf.ned`)

Because INET 4.7.0 defines `Dcf` as a compound `module` containing `channelAccess` (`Dcaf`), `ScheduledDcf` is declared with `module ScheduledDcf extends Dcf`:

```ned
import inet.linklayer.ieee80211.mac.coordinationfunction.Dcf;

module ScheduledDcf extends Dcf
{
    parameters:
        @class(inet::ieee80211::ScheduledDcf);
        int slotIndex = default(0);
        int slotStride = default(1);
        int numAssignedSlots = default(1);
        double slotDuration @unit(s) = default(400us);
        double superframeDuration @unit(s) = default(5ms);
        double cyclePhaseOffset @unit(s) = default(0us);
        double requiredExchangeTime @unit(s) = default(260us);
}
```

### 4.2 Mandatory 64-Bit Fixed-Point Integer Timing (`simtime_t::raw()`)

1. **IEEE 754 Modulo Prohibition:** Floating-point `std::fmod(0.1, 0.02)` evaluates to `0.01999999999999998`, misclassifying slot 0 as the end of the superframe (`docs/results.md` §3.3).
2. **Exact Integer Implementation:** Both `isWithinActiveSlot(simtime_t now)` and `computeNextSlotStart(simtime_t now)` operate exclusively on 64-bit signed integer raw ticks (`int64_t`):
```cpp
int64_t deltaRaw = (now.raw() - cyclePhaseOffset.raw()) % superframeDuration.raw();
if (deltaRaw < 0) deltaRaw += superframeDuration.raw();
```
3. **Core Method Overrides:**
   - `processUpperFrame(Packet *packet, const Ptr<const Ieee80211DataOrMgmtHeader>& header)`: If `isWithinActiveSlot(simTime())` is true, delegates to `Dcf::processUpperFrame`; otherwise enqueues packet into `channelAccess->getPendingQueue()` without requesting the channel and schedules `slotStartTimer`.
   - `channelGranted(IChannelAccess *grantedAccess)`: If `!isWithinActiveSlot(simTime())`, releases the channel via `channelAccess->releaseChannel(this)` and arms `slotStartTimer`.
   - `frameSequenceFinished()`: Emits `frameSequenceFinishedSignal`, releases the channel, and either requests the channel immediately (if another frame is pending and still within the active slot) or schedules `slotStartTimer` for the next superframe.

---

## 5. Acceptance Criteria (Checklist C6)

1. **Zero Collisions:** At $N = 40$ and $N = 80$, `packetSentToPeerWithRetry == 0` and `packetDropRetryLimitReached == 0` across all wireless interfaces.
2. **Airtime Parity:** In a 1-AMR unloaded test, the `State` frame sequence duration in `Radio_Sched` equals the analytical $\text{CW} = 0$ duration ($258\ \mu\text{s}$ at $54\text{ Mbps}$; $814\ \mu\text{s}$ at $12\text{ Mbps}$) within $2\%$.
3. **Bounded Admission Wait:** Maximum wireless MAC queuing delay for `State` under unsaturated arrival is strictly bounded by $T_{\text{super}}$.
