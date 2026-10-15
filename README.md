# Matrix Factory Twin: Discrete-Event Simulation Study

Discrete-event simulation study evaluating bottleneck migration in hybrid wired (IEEE 802.1Q / IEEE 802.1Qbv TSN) and wireless (IEEE 802.11 / Scheduled Wireless) industrial networks for the **Matrix Factory Twin** digital twin architecture.

* **Institution:** Universidade Federal de Santa Catarina (UFSC) — Department of Informatics and Statistics (INE)
* **Authors:** Breno da Silva Pereira, Gabriel S. Stuart
* **Advisor:** Prof. Dr. Antônio Augusto Medeiros Fröhlich
* **Project Milestone:** P2 Completed & Verified — Ready for P3 4,800-Run Production Campaign

---

## 1. Pinned Environment Versions

To guarantee bit-level reproducibility of statistical summations and queue statistics across Phase 2 and Phase 3:

| Component | Pinned Version / Commit | Notes |
| :--- | :--- | :--- |
| **Operating System** | Linux 6.1.0-52-amd64 x86_64 (Debian 12 Bookworm) | Core simulation platform |
| **C++ Compiler** | GCC 12.2.0 (`Debian 12.2.0-14+deb12u1`) | C++17 support |
| **OMNeT++** | OMNeT++ 6.4.0 (`~/omnetpp-6.4.0`) | Simulation kernel |
| **INET Framework** | INET 4.7.0 (`commit dfe270b21f`) | Protocol models |
| **Python** | Python 3.11+ with venv (`pandas`, `numpy`, `scipy`, `matplotlib`) | Offline analysis |

---

## 2. Six-Cell Comparison Matrix

| Cell | Backbone Technology | Radio Channel Access | Status |
| :---: | :--- | :--- | :---: |
| **Cell 1** | Single FIFO (Best Effort) | IEEE 802.11 CSMA/CA | Verified & Ready |
| **Cell 2** | Single FIFO (Best Effort) | Scheduled Wireless (Spike S1: `ScheduledDcf`) | Verified (0 Collisions @ N=40) |
| **Cell 3** | IEEE 802.1Q Priority (4 classes) | IEEE 802.11 CSMA/CA | Verified & Ready |
| **Cell 4** | IEEE 802.1Q Priority (4 classes) | Scheduled Wireless (Spike S1: `ScheduledDcf`) | Verified & Ready |
| **Cell 5** | IEEE 802.1Qbv Time-Aware Shaper | IEEE 802.11 CSMA/CA | Verified & Ready |
| **Cell 6** | IEEE 802.1Qbv Time-Aware Shaper | Scheduled Wireless (Spike S1: `ScheduledDcf`) | Verified & Ready |

---

## 3. Directory Layout

```text
.
├── analysis/               # Python offline analysis, calibration, and pilot scripts
│   ├── calibrate_80211.py  # 802.11 INET calibration verification (Checklist C5)
│   ├── check_gcl.py        # 22 GCL validation rules (Checklist C8)
│   ├── deadline_metrics.py # Mathematical engine for Definitions A & B
│   ├── export_lookup.py    # Digital Twin lookup table generator (Checklist C3)
│   ├── pilot_run.py        # Statistical pilot run and FIFO knee identification (Checklist C9)
│   ├── verify_c8.py        # Execution rigor & RNG isolation verification (Checklist C8)
│   └── verify_spike_s1.py  # Spike S1 N=40 zero-collision verification (Checklist C6)
├── docs/                   # Architectural decisions, specs, and parameter sheets
│   ├── checklist_secao3.md # Execution roadmap & status of Checklists A1–C11
│   ├── decisions.md        # Formal architectural decisions (Q1–Q8) and mathematical rules
│   ├── parameters.md       # Synchronized simulation parameter catalog
│   ├── SPEC-scheduled-dcf.md # C++ specification for ScheduledDcf TDMA MAC
│   ├── SPEC-deadline-sink.md # C++ specification for DeadlineSink
│   └── SPEC-lookup-ner-integration.md # Java Twin consumption contract
├── simulations/            # OMNeT++ NED and INI configuration files
│   ├── MatrixFactoryNetwork.ned
│   └── omnetpp.ini
├── src/                    # Custom C++ extensions (libmatrixfactory.so)
│   ├── DeadlineSink.cc / .h / .ned
│   └── ScheduledDcf.cc / .h / .ned
├── tests/                  # Pytest unit tests (41 tests passing)
├── Makefile                # Build system for libmatrixfactory.so
└── README.md
```

---

## 4. Quickstart Guide

### Environment Activation
Before building or running any simulations, activate the OMNeT++ and INET environment variables:
```bash
# 1. Activate environment
source $HOME/omnetpp-6.4.0/setenv
export INET_ROOT=$HOME/omnetpp-6.4.0/samples/inet-4.7.0

# 2. Build custom C++ library (ScheduledDcf & DeadlineSink)
make -j$(nproc)

# 3. Run unit tests & verification suites
pytest tests/
python3 analysis/check_gcl.py
python3 analysis/verify_c8.py
python3 analysis/verify_spike_s1.py
python3 analysis/pilot_run.py
```

---

## 4. Documentation Index

- [Operational Rules & Invariants (.agents/AGENTS.md)](.agents/AGENTS.md)
- [Master Schedule & Dependency Roadmap (docs/schedule.md)](docs/schedule.md)
- [Implementation Checklist & Status (docs/checklist_secao3.md)](docs/checklist_secao3.md)
- [Experimental Verification & Results Log (docs/results.md)](docs/results.md)
- [Simulation Parameters Sheet (docs/parameters.md)](docs/parameters.md)
- [Architectural Decisions & Q1–Q8 Log (docs/decisions.md)](docs/decisions.md)
- [ScheduledDcf C++ Specification (docs/SPEC-scheduled-dcf.md)](docs/SPEC-scheduled-dcf.md)
- [DeadlineSink C++ Specification (docs/SPEC-deadline-sink.md)](docs/SPEC-deadline-sink.md)
- [Digital Twin NER Integration Contract (docs/SPEC-lookup-ner-integration.md)](docs/SPEC-lookup-ner-integration.md)
