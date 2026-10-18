# DeadlineSink and experiment accounting specification

## Replication-global clock

`ExperimentCoordinator` draws one phase for each tick period
`T={10,50,500} ms` from RNG 1. All sinks read those three values; sinks never
draw local phases. Consumption uses exact raw-time arithmetic:

`c = phi + ceil((g - phi + L) / T) * T`, with on-time iff `a <= c`.

## Code map

| File / method | Responsibility |
| --- | --- |
| `ExperimentCoordinator::initialize` | Reads the shared filter settings and draws one phase per tick period. |
| `ExperimentCoordinator::handlePacketCreated` | Classifies sources, assigns packet IDs, applies generation-time filters, and attaches the persistent tag. |
| `ExperimentCoordinator::handleQueueEvent` | Records the AP and TSN queue boundary timestamps used by the delay decomposition. |
| `ExperimentCoordinator::handlePacketDropped` / `finish` | Classifies terminal outcomes and records pending packets as late terminations at simulation end. |
| `DeadlineSink::consumePacket` | Extracts generation time from `ExperimentPacketTag` (falling back to `CreationTimeTag`), applies the receive-side filters, evaluates A/B/`B^T` misses, records ZOH staleness or TTL expiration, and registers valid deliveries. |
| `DeadlineSink::recordDomainBreakdown` | Checks required boundaries and splits valid end-to-end delay into wireless, switch, and residual segments. |
| `DeadlineSink::finish` | Writes conservation counters, per-deadline/per-tick miss scalars (`n_miss_A_<D>ms`, `n_miss_B_<D>ms`, `n_miss_B_<D>ms_T<T>ms`, `n_miss_BT_L_eq_T<T>ms`, `n_late_discarded_ttl`), domain/staleness histograms (`stalenessTicks_<T>ms`), and conditional delivery-delay quantiles. |
| `ExperimentPacketTag.msg` | Defines the persistent packet identity, class, validity, generation time, and domain-boundary fields. |

`computeConsumptionTickRaw` in both C++ modules implements ceiling division in raw `simtime_t` units. Keep the coordinator and sink filters aligned: the coordinator marks valid generations, while the sink independently checks received packets and the exporter audits that both ledgers agree.

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
