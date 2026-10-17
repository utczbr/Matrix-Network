//
// Matrix Factory Twin - Spike S1: ScheduledDcf Implementation
// Targets OMNeT++ 6.4.0 / INET 4.7.0 (commit dfe270b21f)
// Reference: docs/SPEC-scheduled-dcf.md (Checklist C6)
//

#include "ScheduledDcf.h"

#include <cmath>
#include <limits>
#include "inet/common/ModuleAccess.h"
#include "inet/linklayer/ieee80211/mac/Ieee80211Mac.h"

namespace inet {
namespace ieee80211 {

Define_Module(ScheduledDcf);

ScheduledDcf::~ScheduledDcf()
{
    cancelAndDelete(slotStartTimer);
}

void ScheduledDcf::initialize(int stage)
{
    Dcf::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        numAssignedSlots = std::max(1, (int)par("numAssignedSlots"));
        slotStartOffset = par("slotStartOffset");
        slotStrideTime = par("slotStrideTime");
        slotDuration = par("slotDuration");
        superframeDuration = par("superframeDuration");
        cyclePhaseOffset = par("cyclePhaseOffset");
        requiredExchangeTime = par("requiredExchangeTime");

        if (slotDuration <= SIMTIME_ZERO || slotStrideTime <= SIMTIME_ZERO || superframeDuration <= SIMTIME_ZERO)
            throw cRuntimeError("ScheduledDcf: slotDuration, slotStrideTime, and superframeDuration must be strictly positive.");
        if (slotStartOffset < SIMTIME_ZERO || slotStartOffset + (numAssignedSlots - 1) * slotStrideTime + slotDuration > superframeDuration)
            throw cRuntimeError("ScheduledDcf: assigned slot range does not fit in the superframe.");
        if (requiredExchangeTime > slotDuration)
            throw cRuntimeError("ScheduledDcf: requiredExchangeTime (%s) exceeds slotDuration (%s).",
                    requiredExchangeTime.ustr().c_str(), slotDuration.ustr().c_str());

        slotStartTimer = new cMessage("slotStartTimer");

        WATCH(numSlotDeferrals);
        WATCH(numGrantedInSlot);
        EV_INFO << "ScheduledDcf " << getFullPath() << " slotStartOffset=" << slotStartOffset
                << " superframe=" << superframeDuration << " slotDur=" << slotDuration << endl;
    }
    else if (stage == INITSTAGE_LINK_LAYER) {
        // Note: cwMin = 0 and cwMax = 0 must also be set in omnetpp.ini via
        // **.wlan[*].mac.dcf.channelAccess.cwMin = 0 and cwMax = 0
        // so Dcaf initializes its contention state machine with zero backoff.
    }
}

bool ScheduledDcf::isWithinActiveSlot(simtime_t now) const
{
    const int64_t superRaw = superframeDuration.raw();
    const int64_t slotDurationRaw = slotDuration.raw();
    const int64_t slotStartOffsetRaw = slotStartOffset.raw();
    const int64_t slotStrideRaw = slotStrideTime.raw();
    const int64_t reqSecRaw = requiredExchangeTime.raw();
    const int64_t offsetRaw = cyclePhaseOffset.raw();

    // Normalize into [0, superframe); C++ remainder can be negative before the phase offset.
    int64_t deltaRaw = (now.raw() - offsetRaw) % superRaw;
    if (deltaRaw < 0)
        deltaRaw += superRaw;

    for (int m = 0; m < numAssignedSlots; ++m) {
        int64_t slotStartRaw = slotStartOffsetRaw + m * slotStrideRaw;
        int64_t slotEndRaw = slotStartRaw + slotDurationRaw;

        if (deltaRaw >= slotStartRaw && (slotEndRaw - deltaRaw) >= reqSecRaw) {
            return true;
        }
    }
    return false;
}

simtime_t ScheduledDcf::computeNextSlotStart(simtime_t now) const
{
    const int64_t superRaw = superframeDuration.raw();
    const int64_t slotStartOffsetRaw = slotStartOffset.raw();
    const int64_t slotStrideRaw = slotStrideTime.raw();
    const int64_t offsetRaw = cyclePhaseOffset.raw();
    const int64_t nowRaw = now.raw();

    int64_t deltaRaw = nowRaw - offsetRaw;
    // Floor division finds the containing cycle even when time precedes the phase offset.
    int64_t k = deltaRaw / superRaw;
    if (deltaRaw < 0 && (deltaRaw % superRaw != 0))
        k--;
    int64_t cycleBaseRaw = offsetRaw + k * superRaw;

    int64_t bestNextRaw = -1;

    for (int cycleDelta = 0; cycleDelta <= 2; ++cycleDelta) {
        int64_t baseRaw = cycleBaseRaw + cycleDelta * superRaw;
        for (int m = 0; m < numAssignedSlots; ++m) {
            int64_t candidateStartRaw = baseRaw + slotStartOffsetRaw + m * slotStrideRaw;
            if (candidateStartRaw > nowRaw) {
                if (bestNextRaw == -1 || candidateStartRaw < bestNextRaw)
                    bestNextRaw = candidateStartRaw;
            }
        }
        if (bestNextRaw != -1)
            break;
    }

    if (bestNextRaw == -1) {
        throw cRuntimeError("ScheduledDcf: computeNextSlotStart failed: now=%s, k=%ld, cycleBase=%ld, slotStartOffset=%s",
            now.str().c_str(), (long)k, (long)cycleBaseRaw, slotStartOffset.str().c_str());
    }

    return SimTime::fromRaw(bestNextRaw);
}

void ScheduledDcf::scheduleNextSlotTimer(simtime_t now)
{
    // Keep an earlier wake-up if one is already scheduled; otherwise arm the next eligible slot.
    simtime_t nextStart = computeNextSlotStart(now);
    if (slotStartTimer->isScheduled()) {
        if (slotStartTimer->getArrivalTime() <= nextStart)
            return;
        cancelEvent(slotStartTimer);
    }
    scheduleAt(nextStart, slotStartTimer);
}

void ScheduledDcf::handleMessage(cMessage *msg)
{
    if (msg == slotStartTimer) {
        // Own TDMA slot has started: request the channel if frames are waiting
        // and no frame sequence is already active.
        if (!channelAccess->getPendingQueue()->isEmpty() && !frameSequenceHandler->isSequenceRunning()) {
            channelAccess->requestChannel(this);
        }
    }
    else {
        Dcf::handleMessage(msg);
    }
}

void ScheduledDcf::processUpperFrame(Packet *packet, const Ptr<const Ieee80211DataOrMgmtHeader>& header)
{
    Enter_Method("processUpperFrame(%s)", packet->getName());
    take(packet);

    if (isWithinActiveSlot(simTime())) {
        // Inside active slot with sufficient remaining time: delegate directly to Dcf
        Dcf::processUpperFrame(packet, header);
    }
    else {
        // Outside assigned slot: enqueue in Dcaf's PendingQueue without requesting the channel yet,
        // and arm slotStartTimer for our next slot boundary.
        channelAccess->getPendingQueue()->enqueuePacket(packet);
        numSlotDeferrals++;
        scheduleNextSlotTimer(simTime());
    }
}

void ScheduledDcf::channelGranted(IChannelAccess *grantedAccess)
{
    Enter_Method("channelGranted");
    ASSERT(this->channelAccess == grantedAccess);

    if (!isWithinActiveSlot(simTime())) {
        // Channel was granted outside our assigned slot (or too close to slot end):
        // immediately release without transmitting and wait for our next slot.
        numSlotDeferrals++;
        channelAccess->releaseChannel(this);
        if (!channelAccess->getPendingQueue()->isEmpty())
            scheduleNextSlotTimer(simTime());
        return;
    }

    numGrantedInSlot++;
    Dcf::channelGranted(grantedAccess);
}

void ScheduledDcf::frameSequenceFinished()
{
    Enter_Method("frameSequenceFinished");

    emit(IFrameSequenceHandler::frameSequenceFinishedSignal, frameSequenceHandler->getContext());
    channelAccess->releaseChannel(this);

    if (hasFrameToTransmit()) {
        if (isWithinActiveSlot(simTime())) {
            channelAccess->requestChannel(this);
        }
        else {
            scheduleNextSlotTimer(simTime());
        }
    }
    mac->sendDownPendingRadioConfigMsg();
}

void ScheduledDcf::finish()
{
    cSimpleModule::finish();
    recordScalar("scheduledDcf_numSlotDeferrals", numSlotDeferrals);
    recordScalar("scheduledDcf_numGrantedInSlot", numGrantedInSlot);
}

} // namespace ieee80211
} // namespace inet
