# ScheduledDcf specification

`ScheduledDcf` is an idealized conflict-free access regime built on INET's
non-QoS DCF. It retains PHY framing, DIFS/SIFS, ACKs, and transmission time but
sets contention windows to zero and permits a request only inside an assigned
interval with enough time remaining for a complete exchange.

All cycle and slot arithmetic uses `SimTime::raw()` integers. Floating-point
modulo is forbidden.

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
| `numAssignedSlots` | one for an AMR; multiple contiguous slots for the AP |
| `slotDuration` | duration of this node's slot type |
| `requiredExchangeTime` | calibrated minimum complete frame exchange |
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
