# DeadlineSink and experiment accounting specification

## Replication-global clock

`ExperimentCoordinator` draws one phase for each tick period
`T={10,50,500} ms` from RNG 1. All sinks read those three values; sinks never
draw local phases. Consumption uses exact raw-time arithmetic:

`c = phi + ceil((g - phi + L) / T) * T`, with on-time iff `a <= c`.

The common metric population contains generations with `g >= 5 s` and
`c(g, L=100 ms, T=10 ms) <= 60 s`.

## Persistent packet ledger

At each recognized application source, the coordinator attaches an
`ExperimentPacketTag` to the payload region. Unlike an ordinary packet tag,
this survives Ethernet relay `clearTags()` calls. It contains a unique ID,
class, validity bit, generation time, AP boundary, and TSN-switch queue
arrival/departure.

Every valid generation must end in exactly one bin:

- delivered;
- `Drop_Queue` (`QUEUE_OVERFLOW`);
- `Drop_Retry` (`RETRY_LIMIT_REACHED`);
- `Drop_Other` (another terminal reason); or
- `Late_Termination` (still pending when the run ends).

Overhearing outcomes (`NOT_ADDRESSED_TO_US`, `DUPLICATE_DETECTED`, and
`INCORRECTLY_RECEIVED`) are not terminal application losses. Packet IDs prevent
double counting signals emitted by compound queues or duplicated frames.

## Deadline and late semantics

Definition A compares `a-g` with each deadline. Definition B compares `a` with
the tick consumption instant. State and Telemetry record ZOH staleness. Orders
and DDS record watchdog discard when `a > g + TTL`; the TTL is not rounded to a
tick boundary.

## Domain decomposition

- State wireless domain: generation through enqueue at the AP Ethernet egress.
- Orders wireless domain: enqueue at the AP WLAN pending queue through delivery.
- DDS and Telemetry wireless domain: zero.
- Wired switch domain: first enqueue through final pull in the selected TSN
  switch egress queue hierarchy.
- Wire serialization/propagation/other forwarding: exact nonnegative residual.

These three components must sum to end-to-end delay. A missing tag, a missing
boundary, or overlapping/reversed timestamps aborts the simulation; the sink
does not substitute a generic INET time tag.

## Recorded distribution

The coordinator pools each class across all sinks and records 25 conditional
delay quantiles:

`0, .01, .02, .05, .10, .15, .20, .25, .30, .40, .50, .60, .70, .75,
.80, .85, .90, .92, .95, .97, .98, .99, .995, .999, 1`.

The exporter separately records physical loss and deadline misses.
