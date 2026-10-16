//
// Matrix Factory Twin - hybrid wired/wireless experiment network
//
// Targets OMNeT++ 6.4.0 and INET 4.7.0.
//
// Topology (single star, one TSN switch):
//
//   amr[0..numAmrs-1] ~~802.11~~ ap ---- tsnSwitch ---- fms
//                                            |
//                                    station[0..numStations-1]
//
// Design choices worth knowing:
//  * AMRs talk to the FMS only over the radio (as in the proposal).
//  * The INET AccessPoint has a plain EthernetInterface (no TAS), so the TSN
//    switch sits BEHIND the AP. Wireless-originated frames meet the first gate
//    schedule at the switch egress toward the FMS: this is where the
//    "gate-admission delay" of Section 3.3 is produced and can be measured.
//  * Contended egress ports: tsnSwitch->fms (AMR state + DDS + telemetry) and
//    tsnSwitch->ap (orders only). If you want downlink contention too, add
//    background traffic toward the AP side (not done here).
//
// No `package` line on purpose: put this file at the root of a NED folder.
//

import inet.networks.base.TsnNetworkBase;
import inet.node.ethernet.EthernetLink;
import inet.node.inet.WirelessHost;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;
import inet.node.wireless.AccessPoint;
import inet.physicallayer.wireless.ieee80211.packetlevel.Ieee80211ScalarRadioMedium;
import ExperimentCoordinator;

network MatrixFactoryNetwork extends TsnNetworkBase
{
    parameters:
        int numAmrs = default(10);
        int numStations = default(4);
        double wirelessPhyRate @unit(bps) = default(54Mbps); // single source for PHY and schedule geometry
        *.eth[*].bitrate = default(100Mbps);   // wired rate: calibrate in the pilot
    submodules:
        experimentCoordinator: ExperimentCoordinator {
            @display("p=100,30");
        }
        radioMedium: Ieee80211ScalarRadioMedium {
            @display("p=100,500;is=s");
        }
        fms: TsnDevice {
            @display("p=700,250");
        }
        tsnSwitch: TsnSwitch {
            @display("p=500,250");
        }
        station[numStations]: TsnDevice {
            @display("p=500,420,row,80");
        }
        ap: AccessPoint {
            wlan[*].mgmt.typename = "Ieee80211MgmtApSimplified";   // no association delay
            @display("p=300,250");
        }
        amr[numAmrs]: WirelessHost {
            wlan[*].mgmt.typename = "Ieee80211MgmtStaSimplified";
            wlan[*].agent.typename = "";
            @display("p=100,100,row,60");
        }
    connections:
        fms.ethg++ <--> EthernetLink <--> tsnSwitch.ethg++;
        ap.ethg++ <--> EthernetLink <--> tsnSwitch.ethg++;
        for i = 0..numStations-1 {
            station[i].ethg++ <--> EthernetLink <--> tsnSwitch.ethg++;
        }
}
