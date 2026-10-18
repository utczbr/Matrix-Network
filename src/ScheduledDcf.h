//
// Matrix Factory Twin - Spike S1: ScheduledDcf Header
// Targets OMNeT++ 6.4.0 / INET 4.7.0 (commit dfe270b21f)
// Reference: docs/SPEC-scheduled-dcf.md
//

#ifndef __MATRIXFACTORY_SCHEDULEDDCF_H
#define __MATRIXFACTORY_SCHEDULEDDCF_H

#include "inet/linklayer/ieee80211/mac/coordinationfunction/Dcf.h"

namespace inet {
namespace ieee80211 {

class INET_API ScheduledDcf : public Dcf
{
  protected:
    // TDMA superframe & slot configuration parameters
    int numAssignedSlots = 1;
    simtime_t slotStartOffset = SIMTIME_ZERO;
    simtime_t slotStrideTime = SIMTIME_ZERO;
    simtime_t slotDuration = SIMTIME_ZERO;
    simtime_t superframeDuration = SIMTIME_ZERO;
    simtime_t cyclePhaseOffset = SIMTIME_ZERO;
    simtime_t requiredExchangeTime = SIMTIME_ZERO;

    // Self-timer triggered at the start of the node's next assigned slot
    cMessage *slotStartTimer = nullptr;

    // Instrumentation counters for acceptance verification (Checklist C6)
    long numSlotDeferrals = 0;
    long numDeferredOnEnqueue = 0;
    long numGrantReleased = 0;
    long numGrantedInSlot = 0;

  protected:
    virtual int numInitStages() const override { return NUM_INIT_STAGES; }
    virtual void initialize(int stage) override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    // Returns true iff `now` falls inside one of this node's assigned slots
    // AND the remaining time in that slot is >= requiredExchangeTime.
    virtual bool isWithinActiveSlot(simtime_t now) const;

    // Computes the exact simulation timestamp of the start of the next assigned slot > now.
    virtual simtime_t computeNextSlotStart(simtime_t now) const;

    // Schedules or reschedules `slotStartTimer` for the next assigned slot boundary.
    virtual void scheduleNextSlotTimer(simtime_t now);

    // Overrides from Dcf / IChannelAccess::ICallback / IFrameSequenceHandler::ICallback
    virtual void processUpperFrame(Packet *packet, const Ptr<const Ieee80211DataOrMgmtHeader>& header) override;
    virtual void frameSequenceFinished() override;

  public:
    ScheduledDcf() = default;
    virtual ~ScheduledDcf() override;

    virtual void channelGranted(IChannelAccess *channelAccess) override;
};

} // namespace ieee80211
} // namespace inet

#endif // __MATRIXFACTORY_SCHEDULEDDCF_H
