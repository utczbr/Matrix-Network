# AGENTS.md — Operational Rules & Invariants for Matrix Factory Twin

## 1. Pinned Environment & Build Rules
- **Operating System:** Linux 6.1.0-52-amd64 x86_64 (Debian 12 Bookworm)
- **C++ Compiler:** GCC 12.2.0 (`Debian 12.2.0-14+deb12u1`)
- **OMNeT++ Version:** 6.4.0 (`~/omnetpp-6.4.0` / `$HOME/omnetpp-6.4.0`)
- **INET Framework:** 4.7.0 (`commit dfe270b21f`)
- **Never upgrade** OMNeT++, INET, or GCC during P2, P3, or P4.
- Always compile C++ extensions (`src/ScheduledDcf.*`, `src/DeadlineSink.*`) into `out/gcc-release/libmatrixfactory.so` and load with `-l ../out/gcc-release/matrixfactory`.

## 2. Non-Negotiable Mathematical & Simulation Invariants
1. **64-Bit Fixed-Point Time Arithmetic in `ScheduledDcf` (`simtime_t::raw()`):**
   - NEVER use `std::fmod()` or IEEE 754 `double` modulo arithmetic for TDMA slot boundaries in `src/ScheduledDcf.cc`. Floating-point representation drift (e.g., `fmod(0.1, 0.02) = 0.01999999999999998`) misclassifies slot 0 at superframe boundaries.
   - ALWAYS compute slot offsets and boundaries using 64-bit integer fixed-point ticks via `simtime_t::raw()` and `SimTime::fromRaw()`.
2. **Three-Stream RNG Isolation (Checklist C8):**
   - `rng-0`: Wireless MAC contention backoff and protocol state machines.
   - `rng-1`: Application traffic generators (`**.app[*].source.rng-0 = 1`) and `DeadlineSink` replication phase offset.
   - `rng-2`: AMR spatial coordinates (`*.amr[*].mobility.rng-0 = 2`).
   - Offered load and AMR spatial coordinates must remain bit-identical across all 6 cells for any given seed.
3. **Common Unbiased Horizon Filter & Packet Conservation Law:**
   - Warmup filter: discard packets with generation time `g < 5.0s`.
   - Horizon filter: discard packets whose consumption tick at `L_horizon = 100ms` (`max(D_SPECTRUM_MS)`) and `T_0 = 10ms` exceeds `sim-time-limit` (`c(100ms, 10ms) > 60.0s`). Evaluating all `D in {1, 2, 5, 10, 20, 50, 100} ms` on this single common packet set guarantees monotonicity of `miss_A_D` and `miss_B_D` and ensures `Late_Arrival = miss_A_D - p_loss >= 0`.
   - Conservation law: every analysis and export script MUST assert: `n_total == n_valid_delivered + n_Drop_Queue + n_Drop_Retry + n_Drop_Other` and `n_received_total == n_valid_delivered + n_filtered_warmup + n_filtered_horizon`.
4. **NER Consumption & Late-Arrival Semantics (Q1–Q2 Ground Truth):**
   - Primary tick quantum: `T = 10ms` (`MIN_DT`), with multi-rate evaluation at `T in {10, 50, 500} ms`.
   - Consumption instant: `c = phi + ceil((g - phi + L_c) / T) * T` with `L_c = D_c` (primary) and `L_c = T` (maintainer variant `B^T`), evaluated with non-strict inequality `a <= c`.
   - Late semantics: `orders` and `dds` follow **KILL** (discarded after watchdog TTL); `state` and `telemetry` follow **ZOH** (Zero-Order Hold, excess staleness `Delta_k_stale` recorded in ticks).
5. **Lookup Table & Wasserstein PCHIP Contract (Q3):**
   - Export `lookup_summary.{csv,json}` and `lookup_ecdf.{csv,json}` with conditional delivery delay quantiles and separate `p_loss`.
   - Interpolate horizontally in quantile space (1D Wasserstein geodesic) via `scipy.interpolate.PchipInterpolator`, enforce cumulative maximum non-crossing across quantile levels, clip delays to `>= 0`, clamp post-saturation regimes (`> 100 Mbps` FIFO; `> 44.8 Mbps` TAS telemetry) to nearest neighbor, and never extrapolate outside the grid.

## 3. Documentation Synchronization Rule
Any change to parameters, C++ modules, or analysis scripts must be synchronized in the same commit across `simulations/omnetpp.ini`, `docs/parameters.md`, `docs/decisions.md`, `docs/SPEC-*.md`, and `docs/results.md`.
