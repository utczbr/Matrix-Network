# ScheduledDcf specification

`ScheduledDcf` is an idealized conflict-free access regime built on INET's
non-QoS DCF. It retains PHY framing, DIFS/SIFS, ACKs, and transmission time but
sets contention windows to zero and permits a request only inside an assigned
interval with enough time remaining for a complete exchange.

All cycle and slot arithmetic uses `SimTime::raw()` integers. Floating-point
modulo is forbidden.

## Code map

| Method | Responsibility |
| --- | --- |
| `initialize` | Reads slot geometry and rejects nonpositive durations, out-of-frame allocations, or exchanges too long for a slot. |
| `isWithinActiveSlot` | Maps the current time into the phase-adjusted superframe and checks both slot membership and remaining exchange time. When multiple contiguous slots are assigned (as in the AP downlink allocation), remaining time is evaluated against the end of the entire contiguous block rather than individual sub-slot boundaries. |
| `computeNextSlotStart` | Finds the earliest assigned slot boundary strictly after the current time, including times before the configured phase offset. |
| `scheduleNextSlotTimer` / `handleMessage` | Arms the next boundary and requests channel access when queued frames are waiting. |
| `processUpperFrame` | Sends immediately through DCF when an exchange fits; otherwise queues the frame until its next slot. |
| `channelGranted` / `frameSequenceFinished` | Releases grants received outside an eligible slot and resumes or defers queued transmissions after each sequence. |
| `finish` | Records `scheduledDcf_numSlotDeferrals`, `scheduledDcf_numDeferredOnEnqueue`, `scheduledDcf_numGrantReleased`, and `scheduledDcf_numGrantedInSlot`. |

The acceptance checks in `analysis/verify_spike_s1.py` validate resolved slot parameters, successful scheduled traffic, retry counters, and the State delay bound at nominal and stress points.

The network parameter `wirelessPhyRate` is the single source of truth for the
scheduled slot geometry. The `Point` and `Sweep` configurations bind both it
and every WLAN bitrate to the same `phyRate` iteration variable. Ad-hoc runs
that override the WLAN bitrate must override `*.wirelessPhyRate` as well; the
acceptance script does this and verifies the resolved slot parameters.

## Parameters

| Parameter | Meaning |
| --- | --- |
| `slotStartOffset` | first assigned start within the superframe |
| `slotStrideTime` | distance between starts assigned to the same node |
| `numAssignedSlots` | one for an AMR; multiple contiguous slots for the AP (contiguous slots merge into an uninterrupted transmission window) |
| `slotDuration` | duration of this node's slot type |
| `requiredExchangeTime` | calibrated sequence duration plus DIFS (28 µs); ensures any exchange admitted before the cutoff finishes at least one DIFS before the next slot boundary so INET's `backoffOptimization = true` grants the next slot immediately |
| `superframeDuration` | common cycle, including any padding |
| `cyclePhaseOffset` | phase relative to simulation time zero |

Initialization fails if the required exchange exceeds the slot or the last
assigned interval exceeds the superframe.

## Locked allocation

At 54 Mbps, both directions use 400 µs slots. State requires 260 µs and Orders
200 µs. AP slot counts are 1, 1, 2, 8, and 39; superframes are 3, 5, 9, 20,
and 48 ms for N=5, 10, 20, 40, and 80.

At 12 Mbps, State uses 850 µs slots with an 820 µs requirement and Orders uses
560 µs slots with a 550 µs requirement. The N=80 cycle is no longer than
the 90 ms minimum State interarrival, preventing per-AMR two-packet accumulation.
The allocation is:

| N | AMR slots | AP slots | occupied time | superframe | State service | Orders service |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 1 | 4.81 ms | 6 ms | 166.7/s per AMR | 166.7/s |
| 10 | 10 | 1 | 9.06 ms | 10 ms | 100/s per AMR | 100/s |
| 20 | 20 | 3 | 18.68 ms | 20 ms | 50/s per AMR | 150/s |
| 40 | 40 | 10 | 39.60 ms | 42 ms | 23.8/s per AMR | 238.1/s |
| 80 | 80 | 39 | 89.84 ms | 90 ms | 11.11/s per AMR | 433.3/s |

The offered rates are 10 State/s per AMR and `5N` Orders/s. Thus every point
has service at or above offered load; the N=80, 12 Mbps point is intentionally
the tight stress case.

## Acceptance gates

- Exact retry and retry-limit *count* scalars are present and zero in scheduled
  cells, while the CSMA control has traffic and retry activity.
- `packetSentToPeer:count` is nonzero; byte-sum siblings must never be added to
  a frame count.
- Maximum State delay satisfies the configured superframe bound plus the stated
  wired margin; the N=80 cycle must not exceed the 90 ms minimum interarrival.
- The N=80, 12 Mbps cell completes without persistent scheduled backlog.

## Contiguous AP Slot Merging and Operating Boundaries (Item 6 & C8)

1. **Contiguous Downlink Block Admission (`ScheduledDcf::isWithinActiveSlot`):**
   `isWithinActiveSlot` merges contiguous slots assigned to the same station (`nextStartRaw == blockEndRaw`). Consequently, at 12 Mbps, the single-slot duration $s_{\text{AP}} = 560\ \mu\text{s}$ (`requiredExchangeTime = 550 us`) bounds the entire AP downlink window only when `numAssignedSlots == 1` ($N \in \{5, 10\}$); for $N \in \{20, 40, 80\}$, the AP merges $K \in \{3, 10, 39\}$ contiguous slots into a single window of $1.68\ \text{ms}$, $5.60\ \text{ms}$, or $21.84\ \text{ms}$, and the $550\ \mu\text{s}$ remaining-time check applies only at the trailing edge of the merged block.
2. **Schedule Operating Limit at $N = 80, 12\ \text{Mbps}$ (Item 6):**
   At $N = 80, 12\ \text{Mbps}$, the superframe is $T_{\text{super}} = 90\ \text{ms}$ ($89.84\ \text{ms}$ occupied), which keeps per-AMR service ($11.11\ \text{pkts/s}$) above the $10\ \text{Hz}$ offered `State` rate and meets the $100\ \text{ms}$ deadline threshold with zero collisions, but exceeds the nominal $D_{\text{state}} = 50\ \text{ms}$ budget (yielding a maximum observed `State` delay of $90.876\ \text{ms}$ in `verify_spike_s1.py`). This is documented as an explicit operating limit of the configured single-slot-per-AMR schedule at $12\ \text{Mbps}$ for a $50\ \text{ms}$ budget, not a general impossibility bound for static TDMA or wireless TSN.
3. **Phase lattice (C9).** The ideal slot-start lattice modulo the `1000 us` GCL has `1000 / gcd(s_AMR, 1000)` residues (`5` at 54 Mbps, `20` at 12 Mbps); a fleet of `N` populates at most `min(N, 5)` or `min(N, 20)` of them, before airtime and AP forwarding shift actual switch arrivals.
4. **Operating-limit matrix.** `docs/capacity.md` §6 lists, for every `(N, PHY)` pair and `D in {1, 2, 5, 10, 20, 50, 100} ms`, whether `T_super <= D`; the implied miss fractions are uniform-phase estimates (`Derive`), not measurements.
