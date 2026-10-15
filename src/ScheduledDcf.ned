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
        int slotIndex = default(0);                        // 0..N-1 for AMRs; N for AP start slot
        int slotStride = default(1);                       // Contiguous (1) or interleaved stride for multi-slot nodes
        int numAssignedSlots = default(1);                 // 1 for AMR; 1, 2, 8, or 39 for AP downlink
        double slotDuration @unit(s) = default(400us);     // 400us @ 54Mbps, 1000us @ 12Mbps
        double superframeDuration @unit(s) = default(5ms); // Integer multiple of 1ms TAS cycle
        double cyclePhaseOffset @unit(s) = default(0us);   // Phase offset relative to wired TAS GCL
        double requiredExchangeTime @unit(s) = default(260us); // 258us @ 54Mbps, 814us @ 12Mbps
}
