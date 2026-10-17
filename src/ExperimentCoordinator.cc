#include "ExperimentCoordinator.h"

#include <algorithm>
#include <cstring>
#include <cmath>
#include <iomanip>
#include <sstream>

#include "ExperimentPacketTag_m.h"
#include "inet/common/Simsignals.h"
#include "inet/common/Simsignals_m.h"

namespace inet {

Define_Module(ExperimentCoordinator);

constexpr std::array<int, ExperimentCoordinator::NUM_TICK_PERIODS> ExperimentCoordinator::TICK_PERIODS_MS;
constexpr std::array<const char *, ExperimentCoordinator::NUM_CLASSES> ExperimentCoordinator::CLASS_NAMES;

int64_t ExperimentCoordinator::computeConsumptionTickRaw(int64_t gRaw, int64_t leadRaw, int64_t tickRaw, int64_t phiRaw)
{
    // simtime_t raw values share one fixed-point unit, preserving exact grid boundaries.
    const int64_t numerator = gRaw - phiRaw + leadRaw;
    int64_t quotient = numerator / tickRaw;
    if (numerator % tickRaw > 0)
        quotient++;
    return phiRaw + quotient * tickRaw;
}

int ExperimentCoordinator::classIndexFromSource(const char *path)
{
    // Keep classification tied to configured source paths; unrelated packets stay untagged.
    const std::string p(path);
    if (p.find(".amr[") != std::string::npos && p.find(".app[0].source") != std::string::npos)
        return 2;
    if (p.find(".station[") != std::string::npos && p.find(".app[0].source") != std::string::npos)
        return 1;
    if (p.find(".station[") != std::string::npos && p.find(".app[1].source") != std::string::npos)
        return 3;
    const auto fms = p.find(".fms.app[");
    if (fms != std::string::npos && p.find(".source", fms) != std::string::npos) {
        const auto begin = fms + std::strlen(".fms.app[");
        const auto end = p.find(']', begin);
        if (end != std::string::npos && std::stoi(p.substr(begin, end - begin)) >= 3)
            return 0;
    }
    return -1;
}

Ptr<const ExperimentPacketTag> ExperimentCoordinator::findTag(const Packet *packet)
{
    const auto tags = packet->getAllRegionTags<ExperimentPacketTag>();
    return tags.empty() ? nullptr : tags.front().getTag();
}

void ExperimentCoordinator::updateDomainTag(Packet *packet, const std::function<void(const Ptr<ExperimentPacketTag>&)>& update)
{
    packet->mapAllRegionTagsForUpdate<ExperimentPacketTag>(b(0), packet->getTotalLength(),
        [&] (b, b, const Ptr<ExperimentPacketTag>& tag) { update(tag); });
}

void ExperimentCoordinator::initialize(int stage)
{
    cSimpleModule::initialize(stage);
    if (stage != INITSTAGE_LOCAL)
        return;

    warmupTime = par("warmupTime");
    simTimeLimit = par("simTimeLimit");
    horizonLeadTime = par("horizonLeadTime");
    const bool randomize = par("randomizeTickPhase");
    const int rngIndex = par("phaseRngIndex");
    for (size_t i = 0; i < NUM_TICK_PERIODS; ++i) {
        const simtime_t period = SimTime(TICK_PERIODS_MS[i], SIMTIME_MS);
        tickPeriodRaw[i] = period.raw();
        tickPhaseRaw[i] = randomize ? SimTime(uniform(0.0, period.dbl(), rngIndex)).raw() : 0;
    }

    auto root = getSimulation()->getSystemModule();
    root->subscribe(packetCreatedSignal, this);
    // PacketQueue emits packetPushStarted/packetPulled. packetPushed is emitted
    // by sources, classifiers, and sinks, but not by the queue itself.
    root->subscribe(packetPushStartedSignal, this);
    root->subscribe(packetPulledSignal, this);
    root->subscribe(packetDroppedSignal, this);
}

void ExperimentCoordinator::handlePacketCreated(cComponent *source, Packet *packet)
{
    const int classIndex = classIndexFromSource(source->getFullPath().c_str());
    if (classIndex < 0)
        return;

    const int64_t packetId = nextPacketId++;
    const int64_t generationRaw = simTime().raw();
    generatedTotal[classIndex]++;

    // Apply the common warmup and worst-case consumption-horizon filters once at generation.
    bool valid = true;
    if (generationRaw < warmupTime.raw()) {
        filteredWarmup[classIndex]++;
        valid = false;
    }
    else {
        const int64_t consumptionRaw = computeConsumptionTickRaw(generationRaw, horizonLeadTime.raw(), tickPeriodRaw[0], tickPhaseRaw[0]);
        if (consumptionRaw > simTimeLimit.raw()) {
            filteredHorizon[classIndex]++;
            valid = false;
        }
    }

    auto tag = packet->addRegionTag<ExperimentPacketTag>();
    tag->setPacketId(packetId);
    tag->setTrafficClass(CLASS_NAMES[classIndex]);
    tag->setValidForMetrics(valid);
    tag->setGenerationTime(simTime());
    if (valid) {
        generatedValid[classIndex]++;
        validPackets.emplace(packetId, PacketRecord{classIndex, PENDING});
    }
}

void ExperimentCoordinator::handleQueueEvent(cComponent *source, Packet *packet, bool pushed)
{
    if (findTag(packet) == nullptr)
        return;
    const std::string path = source->getFullPath();

    if (path.find(".tsnSwitch.eth[") != std::string::npos && path.find(".macLayer.queue") != std::string::npos) {
        updateDomainTag(packet, [&] (const Ptr<ExperimentPacketTag>& tag) {
            if (pushed && tag->getSwitchQueueArrivalTime() < SIMTIME_ZERO)
                tag->setSwitchQueueArrivalTime(simTime());
            else if (!pushed && tag->getSwitchQueueArrivalTime() >= SIMTIME_ZERO)
                tag->setSwitchQueueDepartureTime(simTime());
        });
    }

    const auto tag = findTag(packet);
    if (!pushed || tag == nullptr || tag->getApBoundaryTime() >= SIMTIME_ZERO)
        return;
    const std::string trafficClass = tag->getTrafficClass();
    // AccessPoint uses the legacy EthernetInterface, whose egress queue is
    // ap.eth[i].queue (unlike the modular switch queue below macLayer).
    const bool stateBoundary = trafficClass == "state" && path.find(".ap.eth[") != std::string::npos && path.find(".queue") != std::string::npos;
    const bool ordersBoundary = trafficClass == "orders" && path.find(".ap.wlan[") != std::string::npos && path.find(".pendingQueue") != std::string::npos;
    if (stateBoundary || ordersBoundary)
        updateDomainTag(packet, [&] (const Ptr<ExperimentPacketTag>& mutableTag) { mutableTag->setApBoundaryTime(simTime()); });
}

void ExperimentCoordinator::handlePacketDropped(Packet *packet, cObject *details)
{
    const auto tag = findTag(packet);
    if (tag == nullptr || !tag->getValidForMetrics())
        return;
    auto recordIt = validPackets.find(tag->getPacketId());
    if (recordIt == validPackets.end() || recordIt->second.outcome != PENDING)
        return;

    auto dropDetails = dynamic_cast<PacketDropDetails *>(details);
    if (dropDetails == nullptr)
        return;
    const auto reason = dropDetails->getReason();
    // These radio outcomes describe overhearing, not a terminal loss of the application packet.
    if (reason == NOT_ADDRESSED_TO_US || reason == DUPLICATE_DETECTED || reason == INCORRECTLY_RECEIVED)
        return;

    const int c = recordIt->second.classIndex;
    if (reason == QUEUE_OVERFLOW) {
        recordIt->second.outcome = DROP_QUEUE;
        dropQueue[c]++;
    }
    else if (reason == RETRY_LIMIT_REACHED) {
        recordIt->second.outcome = DROP_RETRY;
        dropRetry[c]++;
    }
    else {
        recordIt->second.outcome = DROP_OTHER;
        dropOther[c]++;
    }
}

void ExperimentCoordinator::receiveSignal(cComponent *source, simsignal_t signal, cObject *object, cObject *details)
{
    auto packet = dynamic_cast<Packet *>(object);
    if (packet == nullptr)
        return;
    if (signal == packetCreatedSignal)
        handlePacketCreated(source, packet);
    else if (signal == packetPushStartedSignal)
        handleQueueEvent(source, packet, true);
    else if (signal == packetPulledSignal)
        handleQueueEvent(source, packet, false);
    else if (signal == packetDroppedSignal)
        handlePacketDropped(packet, details);
}

int64_t ExperimentCoordinator::getTickPhaseRaw(size_t index) const
{
    if (index >= NUM_TICK_PERIODS)
        throw cRuntimeError("ExperimentCoordinator: invalid tick-period index %zu", index);
    return tickPhaseRaw[index];
}

void ExperimentCoordinator::markDelivered(int64_t packetId, double delayMs)
{
    auto it = validPackets.find(packetId);
    if (it == validPackets.end())
        throw cRuntimeError("ExperimentCoordinator: delivered packet id %ld is absent from the valid-generation ledger", (long)packetId);
    if (it->second.outcome != PENDING)
        throw cRuntimeError("ExperimentCoordinator: packet id %ld has more than one terminal outcome", (long)packetId);
    it->second.outcome = DELIVERED;
    deliveredValid[it->second.classIndex]++;
    deliveredDelaysMs[it->second.classIndex].push_back(delayMs);
}

void ExperimentCoordinator::recordClassScalar(const char *prefix, const std::array<long, NUM_CLASSES>& values)
{
    for (size_t i = 0; i < NUM_CLASSES; ++i) {
        const std::string name = std::string(prefix) + "_" + CLASS_NAMES[i];
        recordScalar(name.c_str(), values[i]);
    }
}

void ExperimentCoordinator::finish()
{
    // Valid packets still pending at the run boundary are recorded as late terminations.
    std::array<long, NUM_CLASSES> lateTermination = {};
    for (const auto& entry : validPackets)
        if (entry.second.outcome == PENDING)
            lateTermination[entry.second.classIndex]++;

    recordClassScalar("n_generated_total", generatedTotal);
    recordClassScalar("n_generated_valid", generatedValid);
    recordClassScalar("n_filtered_warmup", filteredWarmup);
    recordClassScalar("n_filtered_horizon", filteredHorizon);
    recordClassScalar("n_delivered_valid", deliveredValid);
    recordClassScalar("n_drop_queue", dropQueue);
    recordClassScalar("n_drop_retry", dropRetry);
    recordClassScalar("n_drop_other", dropOther);
    recordClassScalar("n_late_termination", lateTermination);
    for (size_t i = 0; i < NUM_TICK_PERIODS; ++i) {
        const std::string name = "tick_phase_offset_" + std::to_string(TICK_PERIODS_MS[i]) + "ms_sec";
        recordScalar(name.c_str(), SimTime::fromRaw(tickPhaseRaw[i]).dbl());
    }
    static constexpr std::array<double, 25> levels = {
        0.000, 0.010, 0.020, 0.050, 0.100, 0.150, 0.200, 0.250,
        0.300, 0.400, 0.500, 0.600, 0.700, 0.750, 0.800, 0.850,
        0.900, 0.920, 0.950, 0.970, 0.980, 0.990, 0.995, 0.999, 1.000
    };
    for (size_t c = 0; c < NUM_CLASSES; ++c) {
        auto& delays = deliveredDelaysMs[c];
        if (delays.empty())
            continue;
        // Interpolate empirical quantiles from pooled, sorted delivered-delay samples.
        std::sort(delays.begin(), delays.end());
        for (double q : levels) {
            const double position = q * (delays.size() - 1);
            const size_t lo = static_cast<size_t>(std::floor(position));
            const size_t hi = static_cast<size_t>(std::ceil(position));
            const double value = delays[lo] + (position - lo) * (delays[hi] - delays[lo]);
            std::ostringstream name;
            name << "ecdf_" << CLASS_NAMES[c] << "_q_" << std::fixed << std::setprecision(3) << q;
            recordScalar(name.str().c_str(), value);
        }
    }
    cSimpleModule::finish();
}

} // namespace inet
