import inet.queueing.source.ActivePacketSource;
import inet.queueing.contract.IActivePacketSource;

simple ExperimentPacketSource extends ActivePacketSource like IActivePacketSource
{
    parameters:
        @statistic[generationEvents](title="application packet generation events";
            source=packetCreated; record=count,vector(packetBytes); unit=pk;
            interpolationmode=none);
}
