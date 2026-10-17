// Persistent application-packet identity and domain-boundary timestamps.
// Region tags survive protocol encapsulation and Ethernet relay tag clearing.

import inet.common.INETDefs;
import inet.common.TagBase;

namespace inet;

class ExperimentPacketTag extends TagBase
{
    // Packet identity and metric eligibility persist across encapsulation and relay tag clearing.
    int64 packetId = -1;
    string trafficClass;
    bool validForMetrics = false;
    simtime_t generationTime = -1;
    // Set at the AP and selected TSN egress queue boundaries for domain delay attribution.
    simtime_t apBoundaryTime = -1;
    simtime_t switchQueueArrivalTime = -1;
    simtime_t switchQueueDepartureTime = -1;
}
