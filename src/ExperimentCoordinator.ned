import inet.common.INETDefs;

simple ExperimentCoordinator
{
    parameters:
        @class(inet::ExperimentCoordinator);
        double warmupTime @unit(s) = default(5s);
        double simTimeLimit @unit(s) = default(60s);
        double horizonLeadTime @unit(s) = default(100ms);
        // One phase draw per configured tick period is shared by every DeadlineSink.
        bool randomizeTickPhase = default(true);
        int phaseRngIndex = default(1);
        @display("i=block/control");
}
