//
// Matrix Factory Twin - Spike S1: Conflict-Free Scheduled IEEE 802.11 Access
// Drop-in replacement for inet.linklayer.ieee80211.mac.coordinationfunction.Dcf
// Reference: docs/SPEC-scheduled-dcf.md (Checklist C6)
//

import inet.linklayer.ieee80211.mac.coordinationfunction.Dcf;

module ScheduledDcf extends Dcf
{
    parameters:
        @class(inet::ieee80211::ScheduledDcf);
        int numAssignedSlots = default(1);                 // one AMR slot or multiple AP downlink slots
        double slotStartOffset @unit(s) = default(0us);    // first slot start within the superframe
        double slotStrideTime @unit(s) = default(400us);   // distance between this node's slot starts
        double slotDuration @unit(s) = default(400us);     // may differ for State uplink and Orders downlink
        double superframeDuration @unit(s) = default(5ms); // Integer multiple of 1ms TAS cycle
        double cyclePhaseOffset @unit(s) = default(0us);   // Phase offset relative to wired TAS GCL
        double requiredExchangeTime @unit(s) = default(260us); // 258us @ 54Mbps, 814us @ 12Mbps
}
