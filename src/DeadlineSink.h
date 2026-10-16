//
// Matrix Factory Twin - DeadlineSink Header
// Targets OMNeT++ 6.4.0 / INET 4.7.0 (commit dfe270b21f)
// Reference: docs/SPEC-deadline-sink.md (Checklist C7)
//

#ifndef __MATRIXFACTORY_DEADLINESINK_H
#define __MATRIXFACTORY_DEADLINESINK_H

#include <array>
#include <cstdint>
#include <string>
#include <vector>
#include "inet/queueing/sink/PassivePacketSink.h"

namespace inet {
class ExperimentCoordinator;
class ExperimentPacketTag;
namespace queueing {

class INET_API DeadlineSink : public PassivePacketSink
{
  public:
    static constexpr size_t NUM_DEADLINES = 7;
    static constexpr size_t NUM_TICK_PERIODS = 3;
    static constexpr size_t NUM_QUANTILES = 25;

    // 7 standardized deadline thresholds D_k (ms): {1, 2, 5, 10, 20, 50, 100} ms
    static constexpr std::array<int, NUM_DEADLINES> DEADLINE_SPECTRUM_MS = {
        1, 2, 5, 10, 20, 50, 100
    };

    // 3 NER tick periods T_m (ms): {10, 50, 500} ms
    static constexpr std::array<int, NUM_TICK_PERIODS> TICK_PERIODS_MS = {
        10, 50, 500
    };

    // 25 quantile levels (24 intervals from 0.000 to 1.000; contains the 15-level subset)
    static constexpr std::array<double, NUM_QUANTILES> QUANTILE_LEVELS = {
        0.000, 0.010, 0.020, 0.050, 0.100, 0.150, 0.200, 0.250,
        0.300, 0.400, 0.500, 0.600, 0.700, 0.750, 0.800, 0.850,
        0.900, 0.920, 0.950, 0.970, 0.980, 0.990, 0.995, 0.999,
        1.000
    };

  protected:
    // Configuration parameters
    std::string trafficClass;
    simtime_t nominalDeadline = SIMTIME_ZERO;
    simtime_t appWatchdogTtl = SIMTIME_ZERO;
    simtime_t horizonLeadTime = SIMTIME_ZERO;
    bool isZohFlow = true;
    simtime_t warmupTime = SIMTIME_ZERO;
    simtime_t simTimeLimit = SIMTIME_ZERO;
    ExperimentCoordinator *experimentCoordinator = nullptr;

    // Precomputed 64-bit raw SimTime constants for exact integer grid evaluation
    std::array<int64_t, NUM_DEADLINES> deadlineRaw = {};
    std::array<int64_t, NUM_TICK_PERIODS> tickPeriodRaw = {};
    std::array<int64_t, NUM_TICK_PERIODS> tickPhaseRaw = {};

    // Accounting & packet conservation counters
    long nReceivedTotal = 0;
    long nFilteredWarmup = 0;
    long nFilteredHorizon = 0;
    long nValidDelivered = 0;
    long nOnTimeNominalA = 0;
    long nOnTimeNominalB = 0;
    long nLateNominalA = 0;
    long nLateNominalB = 0;
    long nLateDiscardedTtl = 0;
    long nDomainBreakdownValid = 0;

    // Continuous Definition A counters across D_k
    std::array<long, NUM_DEADLINES> missCountA = {};

    // Discrete Definition B counters (L_k = D_k) across D_k x T_m
    std::array<std::array<long, NUM_TICK_PERIODS>, NUM_DEADLINES> missCountB = {};

    // Maintainer Variant Definition B^T counters (L_c = T_m) across T_m (decisions.md §1.3.2)
    std::array<long, NUM_TICK_PERIODS> missCountBT = {};

    // Histograms & exact delay vector for quantile extraction
    cHistogram e2eDelayHist;
    std::array<cHistogram, NUM_TICK_PERIODS> stalenessTicksHist;
    cHistogram wirelessDomainDelayHist;
    cHistogram wiredSwitchDelayHist;
    cHistogram wireTxAndPropDelayHist;

    std::vector<double> deliveredDelaysMs;

  protected:
    virtual void initialize(int stage) override;
    virtual void consumePacket(Packet *packet) override;
    virtual void finish() override;

    // Exact 64-bit integer ceiling tick computation:
    // cRaw = phiRaw + ceil((gRaw - phiRaw + leadRaw) / tickRaw) * tickRaw
    static int64_t computeConsumptionTickRaw(int64_t gRaw, int64_t leadRaw, int64_t tickRaw, int64_t phiRaw);

    // Extracts packet creation timestamp at the source application
    static simtime_t extractCreationTime(const Packet *packet);

    // Decomposes end-to-end delay into wireless, switch queue/gate, and wire tx/prop segments
    virtual void recordDomainBreakdown(const Packet *packet, simtime_t generationTime, simtime_t arrivalTime);

  public:
    DeadlineSink() = default;
    virtual ~DeadlineSink() override = default;
};

} // namespace queueing
} // namespace inet

#endif // __MATRIXFACTORY_DEADLINESINK_H
