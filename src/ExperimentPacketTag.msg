// Persistent application-packet identity and domain-boundary timestamps.
// Region tags survive protocol encapsulation and Ethernet relay tag clearing.

import inet.common.INETDefs;
import inet.common.TagBase;

namespace inet;

class ExperimentPacketTag extends TagBase
{
    int64 packetId = -1;
    string trafficClass;
    bool validForMetrics = false;
    simtime_t generationTime = -1;
    simtime_t apBoundaryTime = -1;
    simtime_t switchQueueArrivalTime = -1;
    simtime_t switchQueueDepartureTime = -1;
}
