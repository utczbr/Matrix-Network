//
// Matrix Factory Twin - DeadlineSink Implementation
// Targets OMNeT++ 6.4.0 / INET 4.7.0 (commit dfe270b21f)
// Reference: docs/SPEC-deadline-sink.md (Checklist C7, Q1, Q2, Q3)
//

#include "DeadlineSink.h"
#include "ExperimentCoordinator.h"
#include "ExperimentPacketTag_m.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>
#include "inet/common/TimeTag_m.h"

namespace inet {
namespace queueing {

Define_Module(DeadlineSink);

constexpr std::array<int, DeadlineSink::NUM_DEADLINES> DeadlineSink::DEADLINE_SPECTRUM_MS;
constexpr std::array<int, DeadlineSink::NUM_TICK_PERIODS> DeadlineSink::TICK_PERIODS_MS;
constexpr std::array<double, DeadlineSink::NUM_QUANTILES> DeadlineSink::QUANTILE_LEVELS;

void DeadlineSink::initialize(int stage)
{
    PassivePacketSink::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        trafficClass = par("trafficClass").stdstringValue();
        nominalDeadline = par("nominalDeadline");
        appWatchdogTtl = par("appWatchdogTtl");
        horizonLeadTime = par("horizonLeadTime");
        isZohFlow = par("isZohFlow").boolValue();
        warmupTime = par("warmupTime");
        simTimeLimit = par("simTimeLimit");
        experimentCoordinator = check_and_cast<ExperimentCoordinator *>(
            getSimulation()->getSystemModule()->getSubmodule("experimentCoordinator"));

        for (size_t k = 0; k < NUM_DEADLINES; ++k) {
            deadlineRaw[k] = SimTime(DEADLINE_SPECTRUM_MS[k], SIMTIME_MS).raw();
        }

        for (size_t m = 0; m < NUM_TICK_PERIODS; ++m) {
            simtime_t tPeriod = SimTime(TICK_PERIODS_MS[m], SIMTIME_MS);
            tickPeriodRaw[m] = tPeriod.raw();

            tickPhaseRaw[m] = experimentCoordinator->getTickPhaseRaw(m);

            std::string histName = "stalenessTicks_" + std::to_string(TICK_PERIODS_MS[m]) + "ms";
            stalenessTicksHist[m].setName(histName.c_str());
        }

        e2eDelayHist.setName("e2eDelay_ms");
        wirelessDomainDelayHist.setName("wirelessDomainDelay_ms");
        wiredSwitchDelayHist.setName("wiredSwitchDelay_ms");
        wireTxAndPropDelayHist.setName("wireSerializationAndPropDelay_ms");

        deliveredDelaysMs.reserve(32768);
        missCountA.fill(0);
        for (auto& row : missCountB)
            row.fill(0);
        missCountBT.fill(0);
    }
}

int64_t DeadlineSink::computeConsumptionTickRaw(int64_t gRaw, int64_t leadRaw, int64_t tickRaw, int64_t phiRaw)
{
    // Exact 64-bit integer ceiling division for:
    // c = phi + ceil((g - phi + L) / T) * T
    // Signed division truncates toward zero; the positive-remainder adjustment implements ceil.
    int64_t num = gRaw - phiRaw + leadRaw;
    int64_t q = num / tickRaw;
    int64_t r = num % tickRaw;
    if (r > 0)
        q += 1;
    return phiRaw + q * tickRaw;
}

simtime_t DeadlineSink::extractCreationTime(const Packet *packet)
{
    for (int i = 0; i < packet->getNumRegionTags(); ++i) {
        auto tag = packet->getRegionTag(i);
        if (auto creationTag = dynamicPtrCast<const CreationTimeTag>(tag)) {
            return creationTag->getCreationTime();
        }
    }
    return packet->getCreationTime();
}

void DeadlineSink::recordDomainBreakdown(const Packet *packet, simtime_t generationTime, simtime_t arrivalTime)
{
    const auto tags = packet->getAllRegionTags<ExperimentPacketTag>();
    if (tags.empty())
        throw cRuntimeError("DeadlineSink: application packet arrived without ExperimentPacketTag");
    const auto tag = tags.front().getTag();
    if (tag->getTrafficClass() != trafficClass)
        throw cRuntimeError("DeadlineSink: packet class '%s' arrived at '%s' sink",
            tag->getTrafficClass(), trafficClass.c_str());

    // State crosses the radio before the AP; Orders crosses it after the AP on downlink.
    const bool wirelessFlow = trafficClass == "state" || trafficClass == "orders";
    if (wirelessFlow && tag->getApBoundaryTime() < SIMTIME_ZERO)
        throw cRuntimeError("DeadlineSink: missing AP boundary timestamp for %s packet id %ld",
            trafficClass.c_str(), (long)tag->getPacketId());
    if (tag->getSwitchQueueArrivalTime() < SIMTIME_ZERO || tag->getSwitchQueueDepartureTime() < SIMTIME_ZERO)
        throw cRuntimeError("DeadlineSink: missing switch queue timestamps for %s packet id %ld",
            trafficClass.c_str(), (long)tag->getPacketId());

    const simtime_t switchDelay = tag->getSwitchQueueDepartureTime() - tag->getSwitchQueueArrivalTime();
    simtime_t wirelessDelay = SIMTIME_ZERO;
    if (trafficClass == "state")
        wirelessDelay = tag->getApBoundaryTime() - generationTime;
    else if (trafficClass == "orders")
        wirelessDelay = arrivalTime - tag->getApBoundaryTime();
    const simtime_t e2eDelay = arrivalTime - generationTime;
    const simtime_t wireOtherDelay = e2eDelay - switchDelay - wirelessDelay;
    if (switchDelay < SIMTIME_ZERO || wirelessDelay < SIMTIME_ZERO || wireOtherDelay < SIMTIME_ZERO)
        throw cRuntimeError("DeadlineSink: overlapping or reversed domain timestamps for %s packet id %ld",
            trafficClass.c_str(), (long)tag->getPacketId());

    wirelessDomainDelayHist.collect(wirelessDelay.dbl() * 1000.0);
    wiredSwitchDelayHist.collect(switchDelay.dbl() * 1000.0);
    wireTxAndPropDelayHist.collect(wireOtherDelay.dbl() * 1000.0);
    nDomainBreakdownValid++;
}

void DeadlineSink::consumePacket(Packet *packet)
{
    nReceivedTotal++;

    const simtime_t gSim = extractCreationTime(packet);
    const simtime_t aSim = simTime();
    const int64_t gRaw = gSim.raw();
    const int64_t aRaw = aSim.raw();
    // Keep deadline comparisons in raw ticks; convert only for reported delay values.
    const int64_t tauRaw = aRaw - gRaw;
    const double tauMs = (aSim - gSim).dbl() * 1000.0;
    const int64_t dNomRaw = nominalDeadline.raw();

    // 1. Warmup Transient Filter (decisions.md §1.5 item 1): discard if g < t_warmup
    if (gRaw < warmupTime.raw()) {
        nFilteredWarmup++;
        PassivePacketSink::consumePacket(packet);
        return;
    }

    // 2. Unbiased Common Horizon Filter (decisions.md §1.5 item 2 & export_lookup.py):
    // Filter on c(L_horizon = 100ms, T_0 = 10ms) > simTimeLimit so all D columns share the exact same packet set.
    const int64_t cHorizonRaw = computeConsumptionTickRaw(gRaw, horizonLeadTime.raw(), tickPeriodRaw[0], tickPhaseRaw[0]);
    if (cHorizonRaw > simTimeLimit.raw()) {
        nFilteredHorizon++;
        PassivePacketSink::consumePacket(packet);
        return;
    }

    // Packet survived both filters -> valid delivered sample
    nValidDelivered++;
    e2eDelayHist.collect(tauMs);
    deliveredDelaysMs.push_back(tauMs);
    const auto experimentTags = packet->getAllRegionTags<ExperimentPacketTag>();
    if (experimentTags.empty() || !experimentTags.front().getTag()->getValidForMetrics())
        throw cRuntimeError("DeadlineSink: delivered sample disagrees with the coordinator validity filter");
    experimentCoordinator->markDelivered(experimentTags.front().getTag()->getPacketId(), tauMs);
    recordDomainBreakdown(packet, gSim, aSim);

    // 3. Nominal Deadline Evaluation (Tier 1 D_c)
    if (tauRaw > dNomRaw)
        nLateNominalA++;
    else
        nOnTimeNominalA++;

    const int64_t cNomT0Raw = computeConsumptionTickRaw(gRaw, dNomRaw, tickPeriodRaw[0], tickPhaseRaw[0]);
    if (aRaw > cNomT0Raw)
        nLateNominalB++;
    else
        nOnTimeNominalB++;

    // 4. Continuous Spectrum Evaluation (Definition A across 7 thresholds)
    for (size_t k = 0; k < NUM_DEADLINES; ++k) {
        if (tauRaw > deadlineRaw[k]) {
            missCountA[k]++;
        }
    }

    // 5. Discrete NER Grid Evaluation (Definition B with L_k = D_k, and B^T with L_c = T_m)
    for (size_t m = 0; m < NUM_TICK_PERIODS; ++m) {
        const int64_t tRaw = tickPeriodRaw[m];
        const int64_t phiRaw = tickPhaseRaw[m];

        for (size_t k = 0; k < NUM_DEADLINES; ++k) {
            const int64_t cTickRaw = computeConsumptionTickRaw(gRaw, deadlineRaw[k], tRaw, phiRaw);
            // Non-strict boundary condition confirmed in MainSimulator.java:422-428:
            // on-time iff a <= c; miss iff a > c.
            if (aRaw > cTickRaw) {
                missCountB[k][m]++;
            }
        }

        // Maintainer variant B^T (L_c = T_m, decisions.md §1.3.2)
        const int64_t cTickBTRaw = computeConsumptionTickRaw(gRaw, tRaw, tRaw, phiRaw);
        if (aRaw > cTickBTRaw) {
            missCountBT[m]++;
        }

        // 6. Late-Arrival Semantics Tracking (ZOH Staleness vs. Watchdog TTL Discard)
        if (isZohFlow) {
            // Staleness counts grid ticks elapsed beyond the packet's target consumption tick.
            const int64_t cArrivalTickRaw = computeConsumptionTickRaw(aRaw, 0, tRaw, phiRaw);
            const int64_t cTargetTickRaw = computeConsumptionTickRaw(gRaw, dNomRaw, tRaw, phiRaw);
            long staleTicks = std::max<long>(0L, (cArrivalTickRaw - cTargetTickRaw) / tRaw);
            stalenessTicksHist[m].collect(static_cast<double>(staleTicks));
        }
    }

    if (!isZohFlow) {
        if (aRaw > gRaw + appWatchdogTtl.raw()) {
            nLateDiscardedTtl++;
        }
    }

    PassivePacketSink::consumePacket(packet);
}

void DeadlineSink::finish()
{
    PassivePacketSink::finish();

    recordScalar("n_received_total", nReceivedTotal);
    recordScalar("n_filtered_warmup", nFilteredWarmup);
    recordScalar("n_filtered_horizon", nFilteredHorizon);
    recordScalar("n_valid_delivered", nValidDelivered);

    recordScalar("n_on_time_nominal_A", nOnTimeNominalA);
    recordScalar("n_on_time_nominal_B_10ms", nOnTimeNominalB);
    recordScalar("n_late_nominal_A", nLateNominalA);
    recordScalar("n_late_nominal_B_10ms", nLateNominalB);
    recordScalar("n_late_discarded_ttl", nLateDiscardedTtl);
    recordScalar("n_domain_breakdown_valid", nDomainBreakdownValid);

    for (size_t m = 0; m < NUM_TICK_PERIODS; ++m) {
        std::string phaseName = "tick_phase_offset_" + std::to_string(TICK_PERIODS_MS[m]) + "ms_sec";
        recordScalar(phaseName.c_str(), SimTime::fromRaw(tickPhaseRaw[m]).dbl());
    }

    for (size_t k = 0; k < NUM_DEADLINES; ++k) {
        std::string nameA = "n_miss_A_" + std::to_string(DEADLINE_SPECTRUM_MS[k]) + "ms";
        recordScalar(nameA.c_str(), missCountA[k]);
    }

    for (size_t m = 0; m < NUM_TICK_PERIODS; ++m) {
        const std::string tSuffix = std::to_string(TICK_PERIODS_MS[m]) + "ms";
        for (size_t k = 0; k < NUM_DEADLINES; ++k) {
            std::string nameB = "n_miss_B_" + std::to_string(DEADLINE_SPECTRUM_MS[k]) + "ms_T" + tSuffix;
            recordScalar(nameB.c_str(), missCountB[k][m]);
            if (m == 0) {
                std::string primaryB = "n_miss_B_" + std::to_string(DEADLINE_SPECTRUM_MS[k]) + "ms";
                recordScalar(primaryB.c_str(), missCountB[k][0]);
            }
        }
        std::string nameBT = "n_miss_BT_L_eq_T" + tSuffix;
        recordScalar(nameBT.c_str(), missCountBT[m]);
    }

    e2eDelayHist.recordAs("e2eDelay_ms");
    wirelessDomainDelayHist.recordAs("wirelessDomainDelay_ms");
    wiredSwitchDelayHist.recordAs("wiredSwitchDelay_ms");
    wireTxAndPropDelayHist.recordAs("wireSerializationAndPropDelay_ms");

    for (size_t m = 0; m < NUM_TICK_PERIODS; ++m) {
        std::string histName = "stalenessTicks_" + std::to_string(TICK_PERIODS_MS[m]) + "ms";
        stalenessTicksHist[m].recordAs(histName.c_str());
    }

    if (!deliveredDelaysMs.empty()) {
        // Linear interpolation uses the empirical order statistics at adjacent ranks.
        std::sort(deliveredDelaysMs.begin(), deliveredDelaysMs.end());
        const size_t n = deliveredDelaysMs.size();

        auto getQuantile = [&](double q) -> double {
            if (q <= 0.0 || n == 1) return deliveredDelaysMs.front();
            if (q >= 1.0) return deliveredDelaysMs.back();
            double pos = q * static_cast<double>(n - 1);
            size_t lo = static_cast<size_t>(std::floor(pos));
            size_t hi = static_cast<size_t>(std::ceil(pos));
            double frac = pos - static_cast<double>(lo);
            return deliveredDelaysMs[lo] + frac * (deliveredDelaysMs[hi] - deliveredDelaysMs[lo]);
        };

        for (size_t i = 0; i < NUM_QUANTILES; ++i) {
            std::ostringstream oss;
            oss << "ecdf_q_" << std::fixed << std::setprecision(3) << QUANTILE_LEVELS[i];
            recordScalar(oss.str().c_str(), getQuantile(QUANTILE_LEVELS[i]));
        }

        recordScalar("lat_p50_ms", getQuantile(0.500));
        recordScalar("lat_p90_ms", getQuantile(0.900));
        recordScalar("lat_p95_ms", getQuantile(0.950));
        recordScalar("lat_p99_ms", getQuantile(0.990));
        recordScalar("lat_p99_9_ms", getQuantile(0.999));
    }
}

} // namespace queueing
} // namespace inet
