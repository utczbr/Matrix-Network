# Matrix Factory Twin: Discrete-Event Simulation Study

Discrete-event simulation study evaluating bottleneck migration in hybrid wired (IEEE 802.1Q / IEEE 802.1Qbv TSN) and wireless (IEEE 802.11 / Scheduled Wireless) industrial networks for the **Matrix Factory Twin** digital twin architecture.

* **Institution:** Universidade Federal de Santa Catarina (UFSC) — Department of Informatics and Statistics (INE)
* **Authors:** Breno da Silva Pereira, Gabriel S. Stuart, Lucas de Mello Kindermann
* **Advisor:** Prof. Dr. Antônio Augusto Medeiros Fröhlich
* **Project Milestone:** P2 — Six-cell comparative evaluation & scheduled wireless spike

---

## 1. Pinned Environment Versions

To guarantee bit-level reproducibility of statistical summations and queue statistics across Phase 2 and Phase 3:

| Component | Pinned Version / Commit | Notes |
| :--- | :--- | :--- |
| **Operating System** | Linux 6.1.0-52-amd64 x86_64 (Debian 12 Bookworm) | Core simulation platform |
| **C++ Compiler** | GCC 12.2.0 (`Debian 12.2.0-14+deb12u1`) | C++17 support |
| **OMNeT++** | OMNeT++ 6.4.0 (`/home/stuart/omnetpp-6.4.0`) | Simulation kernel |
| **INET Framework** | INET 4.7.0 (`commit dfe270b21f`) | Protocol models |
| **Python** | Python 3.11+ with venv (`pandas`, `numpy`, `scipy`, `matplotlib`) | Offline analysis |

---

## 2. Six-Cell Comparison Matrix

| Cell | Backbone Technology | Radio Channel Access | Status |
| :---: | :--- | :--- | :---: |
| **Cell 1** | Single FIFO (Best Effort) | IEEE 802.11 CSMA/CA | Baseline ready |
| **Cell 2** | Single FIFO (Best Effort) | Scheduled Wireless (Spike S1) | Phase 7 target |
| **Cell 3** | IEEE 802.1Q Priority (4 classes) | IEEE 802.11 CSMA/CA | Baseline ready |
| **Cell 4** | IEEE 802.1Q Priority (4 classes) | Scheduled Wireless (Spike S1) | Phase 7 target |
| **Cell 5** | IEEE 802.1Qbv Time-Aware Shaper | IEEE 802.11 CSMA/CA | Baseline ready |
| **Cell 6** | IEEE 802.1Qbv Time-Aware Shaper | Scheduled Wireless (Spike S1) | Phase 7 target |

---

## 3. Directory Layout

```text
.
├── analysis/               # Python offline analysis, scavetool parsers, plots
├── docs/                   # Parameter catalogs, decisions logs, metric definitions
│   ├── parameters.md       # Full parameter dictionary (placeholder vs confirmed)
│   └── decisions.md        # Mathematical formulas and questions for supervisors
├── results/                # Output .sca, .vec, .vci, and .csv exports (git-ignored)
├── simulations/            # OMNeT++ NED and INI configuration files
│   ├── MatrixFactoryNetwork.ned
│   └── omnetpp.ini
├── src/                    # Custom C++ extensions (ScheduledDcf, DeadlineSink)
├── Matrix Factory TwinImplementation Guide.md
├── project_design.pdf
└── README.md
```

---

## 4. Quickstart Guide

### Environment Activation
Before building or running any simulations, activate the OMNeT++ and INET environment variables:
```bash
source /home/stuart/omnetpp-6.4.0/setenv
source /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/setenv
```

### Running Simulations
All simulation runs are launched from the `simulations/` directory:

```bash
cd simulations

# Run Cell 1 in headless/command-line mode
opp_run -n /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/src:. \
        -l /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/src/INET \
        -c Cell1 -u Cmdenv omnetpp.ini

# Run with Qtenv GUI for inspection
opp_run -n /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/src:. \
        -l /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/src/INET \
        -c Cell1 -u Qtenv omnetpp.ini
```

### Running Parameter Sweeps
```bash
cd simulations

# List all run configurations for a sweep
opp_run -n /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/src:. \
        -l /home/stuart/omnetpp-6.4.0/samples/inet-4.7.0/src/INET \
        -c Cell1_Sweep -q runs omnetpp.ini
```

---

## 5. Documentation Links
* [Implementation Guide](file:///home/stuart/Documentos/Learn/NetWork/Matrix/Matrix%20Factory%20TwinImplementation%20Guide.md)
* [Simulation Parameters Sheet](file:///home/stuart/Documentos/Learn/NetWork/Matrix/docs/parameters.md)
* [Decisions & Questions Log](file:///home/stuart/Documentos/Learn/NetWork/Matrix/docs/decisions.md)
