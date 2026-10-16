import inet.common.INETDefs;

simple ExperimentCoordinator
{
    parameters:
        @class(inet::ExperimentCoordinator);
        double warmupTime @unit(s) = default(5s);
        double simTimeLimit @unit(s) = default(60s);
        double horizonLeadTime @unit(s) = default(100ms);
        bool randomizeTickPhase = default(true);
        int phaseRngIndex = default(1);
        @display("i=block/control");
}
