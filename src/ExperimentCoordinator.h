#ifndef __MATRIXFACTORY_EXPERIMENTCOORDINATOR_H
#define __MATRIXFACTORY_EXPERIMENTCOORDINATOR_H

#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "inet/common/INETDefs.h"
#include "inet/common/packet/Packet.h"

namespace inet {

class ExperimentPacketTag;

class INET_API ExperimentCoordinator : public cSimpleModule, public cListener
{
  public:
    static constexpr size_t NUM_CLASSES = 4;
    static constexpr size_t NUM_TICK_PERIODS = 3;
    static constexpr std::array<int, NUM_TICK_PERIODS> TICK_PERIODS_MS = {10, 50, 500};

  protected:
    enum Outcome { PENDING, DELIVERED, DROP_QUEUE, DROP_RETRY, DROP_OTHER };

    struct PacketRecord {
        int classIndex = -1;
        Outcome outcome = PENDING;
    };

    static constexpr std::array<const char *, NUM_CLASSES> CLASS_NAMES = {
        "orders", "dds", "state", "telemetry"
    };

    simtime_t warmupTime = SIMTIME_ZERO;
    simtime_t simTimeLimit = SIMTIME_ZERO;
    simtime_t horizonLeadTime = SIMTIME_ZERO;
    std::array<int64_t, NUM_TICK_PERIODS> tickPeriodRaw = {};
    std::array<int64_t, NUM_TICK_PERIODS> tickPhaseRaw = {};

    int64_t nextPacketId = 0;
    std::map<int64_t, PacketRecord> validPackets;
    std::array<long, NUM_CLASSES> generatedTotal = {};
    std::array<long, NUM_CLASSES> generatedValid = {};
    std::array<long, NUM_CLASSES> filteredWarmup = {};
    std::array<long, NUM_CLASSES> filteredHorizon = {};
    std::array<long, NUM_CLASSES> deliveredValid = {};
    std::array<long, NUM_CLASSES> dropQueue = {};
    std::array<long, NUM_CLASSES> dropRetry = {};
    std::array<long, NUM_CLASSES> dropOther = {};
    std::array<std::vector<double>, NUM_CLASSES> deliveredDelaysMs;

    // Map configured source-module paths to the four experiment traffic classes.
    static int classIndexFromSource(const char *path);
    // Return the first grid point at or after generation time plus lead time.
    static int64_t computeConsumptionTickRaw(int64_t gRaw, int64_t leadRaw, int64_t tickRaw, int64_t phiRaw);
    // Read the persistent application tag, if this packet has one.
    static Ptr<const ExperimentPacketTag> findTag(const Packet *packet);
    // Update a region tag over the full packet payload, which may span several regions.
    static void updateDomainTag(Packet *packet, const std::function<void(const Ptr<ExperimentPacketTag>&)>& update);
    void handlePacketCreated(cComponent *source, Packet *packet);
    void handleQueueEvent(cComponent *source, Packet *packet, bool pushed);
    void handlePacketDropped(Packet *packet, cObject *details);
    void recordClassScalar(const char *prefix, const std::array<long, NUM_CLASSES>& values);

  protected:
    virtual int numInitStages() const override { return NUM_INIT_STAGES; }
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual void receiveSignal(cComponent *source, simsignal_t signal, cObject *object, cObject *details) override;

  public:
    // Expose the replication-wide phase so every sink evaluates the same tick grid.
    int64_t getTickPhaseRaw(size_t index) const;
    // Record a valid delivery once in the coordinator's packet-outcome ledger.
    void markDelivered(int64_t packetId, double delayMs);
};

} // namespace inet

#endif
