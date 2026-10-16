//
// Matrix Factory Twin - Online Application Deadline & Domain Attribution Sink
// Drop-in replacement for inet.queueing.sink.PassivePacketSink inside UdpSinkApp
// Reference: docs/SPEC-deadline-sink.md (Checklist C7, Q1, Q2, Q3)
//

import inet.queueing.sink.PassivePacketSink;

simple DeadlineSink extends PassivePacketSink
{
    parameters:
        @class(inet::queueing::DeadlineSink);
        string trafficClass = default("state");               // "orders", "dds", "state", or "telemetry"
        double nominalDeadline @unit(s) = default(50ms);      // Tier 1 D_c: 50ms (orders/state), 5ms (dds), 100ms (telemetry)
        double appWatchdogTtl @unit(s) = default(50ms);       // Tier 2 TTL watchdog (for orders/dds KILL semantics)
        double horizonLeadTime @unit(s) = default(100ms);     // Common horizon filter lead L_max = 100ms (decisions.md §1.5)
        bool isZohFlow = default(true);                       // true for state/telemetry (ZOH); false for orders/dds (KILL)
        double warmupTime @unit(s) = default(5s);             // Warmup filter cutoff (g < warmupTime)
        double simTimeLimit @unit(s) = default(60s);          // Unbiased horizon filter cutoff (c > simTimeLimit)
        // Tick phases are drawn once per replication by the network-level ExperimentCoordinator.
}
