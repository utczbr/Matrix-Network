---
name: matrix-docs-sync
description: >-
  Audit and synchronize parameters, mathematical formulations, architectural decisions, C++ specifications, and experimental results across simulation configuration files and technical documentation. Use when users update simulation parameters, lock design decisions, prepare milestone hand-offs, or check consistency between INI/NED configs, C++/Python code, and markdown documentation.
---

# Simulation Documentation and Configuration Synchronizer

A systematic audit workflow that enforces single-source-of-truth consistency across discrete-event simulation configuration files (`omnetpp.ini`, `.ned`), custom C++ and Python implementations, formal specifications, parameter sheets, decision logs, and experimental result notebooks.

## When to Use
- Updating any simulation parameter, traffic profile, buffer size, or factor sweep level in `omnetpp.ini` or `.ned` files
- Locking architectural or methodological decisions after supervisor or maintainer feedback
- Preparing milestone deliverables (such as P1, P2, P3, or P4 hand-off packages)
- Auditing a repository for specification drift between markdown docs, C++ headers/sources, and Python analysis scripts

## Steps

### 1. Enforce the Single-Source-of-Truth (SSOT) Document Hierarchy
Assign each project document a distinct, non-overlapping role and eliminate versioned duplicate filenames (such as `*_2.md` or `*_3.md`).

- **`AGENTS.md`**: Operational rules, non-negotiable mathematical invariants, and build/test commands.
- **`docs/decisions.md`**: The WHY — mathematical derivations, closed/open questions log, port contention matrices, and normative citations.
- **`docs/parameters.md`**: The WHAT — every INI, NED, and C++ parameter key, baseline/sweep value, units, and verification status (Placeholder, Decision, Confirmed, Verified).
- **`docs/SPEC-*.md`**: The HOW — exact C++ class hierarchies, NED parameter declarations, state machine algorithms, and Python data schemas.
- **`docs/results.md` and `docs/checklist_secao3.md`**: The EVIDENCE — empirical verification tables, provenance metadata, and milestone completion status.

### 2. Cross-Check Configuration-to-Documentation Parity
Verify that every value in `simulations/omnetpp.ini` and `.ned` files matches `docs/parameters.md` and `docs/decisions.md` character-for-character.

- **Execution & RNGs**: Check `sim-time-limit`, `warmup-period`, `num-rngs`, and per-submodule RNG mappings (`rng-0` protocols, `rng-1` traffic generators, `rng-2` spatial mobility).
- **Traffic Classes**: Check UDP ports, PCP/TC mappings, payload byte lengths, generation interval distributions, initial phase offsets, and destination addresses.
- **Switch & Radio Regimes**: Check queue capacities, GCL durations and offset arrays, TDMA `slotDuration` and `superframeDuration` expressions, and PHY bitrates.
- **Factorial Sweep Grid**: Verify that the number of cells, node density levels, background load levels, PHY rates, and repetitions multiply to the exact run count stated in the schedule and checklist.

### 3. Audit Code-to-Specification Fidelity
Inspect C++ (`src/*.ned`, `src/*.h`, `src/*.cc`) and Python (`analysis/*.py`) files against `docs/SPEC-*.md` to prevent silent implementation drift.

- Verify that NED module types match INET's inheritance hierarchy (for example, `module ScheduledDcf extends Dcf` vs. `simple DeadlineSink extends PassivePacketSink`).
- Confirm that time-critical C++ slot and tick calculations use 64-bit integer fixed-point ticks (`simtime_t::raw()`) rather than floating-point `std::fmod`.
- Verify that quantile level arrays, deadline threshold spectra, and horizon filter lead times match across C++ headers, Python constants, and markdown specifications.

### 4. Validate Empirical Results and Repository Hygiene
Check that all reported results and markdown files meet reproducibility and portability standards.

- Check for arithmetic consistency across calibration and pilot tables (for example, ensuring DATA + SIFS + ACK + DIFS sums match across subsections and capacity scripts).
- Flag any empirical table that reports 0 packet drops under oversaturated offered load ($\rho > 1.0$), and verify that the parser queries both composite queue and per-traffic-class sub-queue scalar paths.
- Convert any machine-specific absolute links (`file:///home/...` or search links) in `README.md` or `docs/*.md` into portable relative Markdown links.
- Promote status badges from Placeholder, Proposed, or Open to Decision, Confirmed, or Verified across all tables once verification scripts pass.

## Gotchas
- **Partial updates in changelogs and summary headers:** When closing open questions or updating quantile counts in the body of `decisions.md` or `schedule.md`, check the top revision banner, changelog bullets, and synchronization checklists at the bottom of the file so residual "still open" or outdated counts do not remain.
- **Author and metadata omissions:** Always cross-check `README.md` author lists and pinned tool versions (OMNeT++, INET commit, GCC, OS) against the project design proposal and `parameters.md` §1.
