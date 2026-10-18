#!/usr/bin/env python3
"""Paired-seed wireless-versus-wired bottleneck migration contrasts.

Consumes ``lookup_replications.csv`` written by ``export_lookup.py``. Positive
effects mean that the second architecture in a contrast lowers the nominal
Definition-B miss rate. Pairing is exact on replication seed and factorial key.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import deadline_metrics as dm

CONDITION = ["class", "N_AMR", "lambda_tel_Mbps", "phy_rate_Mbps"]


def _effect(values: np.ndarray) -> tuple[float, float]:
    return float(np.mean(values)), dm.student_t_halfwidth(values)


def build_contrasts(replications: pd.DataFrame, deadline_ms: int | None = None) -> pd.DataFrame:
    if deadline_ms is not None and deadline_ms not in dm.D_SPECTRUM_MS:
        raise ValueError(f"deadline_ms must be one of {dm.D_SPECTRUM_MS}, got {deadline_ms}")
    required = {"cell", "rep", *CONDITION}
    required.update(f"miss_B_{d}ms" for d in dm.D_SPECTRUM_MS)
    missing = sorted(required - set(replications.columns))
    if missing:
        raise ValueError(f"replication table is missing columns: {missing}")

    rows = []
    for condition, group in replications.groupby(CONDITION, sort=True):
        cls = condition[0]
        d_eval = dm.NOMINAL_D_MS[cls] if deadline_ms is None else int(deadline_ms)
        metric = f"miss_B_{d_eval}ms"
        pivot = group.pivot(index="rep", columns="cell", values=metric)
        if set(pivot.columns) != set(range(1, 7)) or pivot.isna().any().any():
            raise ValueError(f"unpaired or incomplete six-cell data for {condition}")

        # Benefit from scheduled radio at each wired level, then average within seed.
        wireless = ((pivot[1] - pivot[2]) + (pivot[3] - pivot[4]) + (pivot[5] - pivot[6])) / 3.0
        # Benefit from TAS over FIFO at both radio levels.
        wired = ((pivot[1] - pivot[5]) + (pivot[2] - pivot[6])) / 2.0
        priority = ((pivot[1] - pivot[3]) + (pivot[2] - pivot[4])) / 2.0
        tas_after_priority = ((pivot[3] - pivot[5]) + (pivot[4] - pivot[6])) / 2.0
        difference = wireless - wired

        wireless_mean, wireless_ci = _effect(wireless.to_numpy())
        wired_mean, wired_ci = _effect(wired.to_numpy())
        priority_mean, priority_ci = _effect(priority.to_numpy())
        tas_mean, tas_ci = _effect(tas_after_priority.to_numpy())
        difference_mean, difference_ci = _effect(difference.to_numpy())
        if np.all(pivot.to_numpy() == 0.0):
            dominant = "none_or_uncongested"
        elif difference_mean - difference_ci > 0:
            dominant = "wireless"
        elif difference_mean + difference_ci < 0:
            dominant = "wired"
        else:
            dominant = "mixed_or_uncertain"

        rows.append({
            **dict(zip(CONDITION, condition)),
            "n_paired_reps": len(pivot),
            "wireless_gain": wireless_mean,
            "ci95_wireless_gain": wireless_ci,
            "wired_fifo_to_tas_gain": wired_mean,
            "ci95_wired_fifo_to_tas_gain": wired_ci,
            "wired_fifo_to_priority_gain": priority_mean,
            "ci95_wired_fifo_to_priority_gain": priority_ci,
            "wired_priority_to_tas_gain": tas_mean,
            "ci95_wired_priority_to_tas_gain": tas_ci,
            "wireless_minus_wired": difference_mean,
            "ci95_wireless_minus_wired": difference_ci,
            "dominant_bottleneck": dominant,
        })
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("replications_csv", type=Path)
    parser.add_argument("--out", type=Path, default=Path("bottleneck_migration.csv"))
    parser.add_argument("--deadline-ms", type=int, default=None,
                        help="override class nominal deadline with a fixed D from D_SPECTRUM_MS")
    args = parser.parse_args(argv)
    result = build_contrasts(pd.read_csv(args.replications_csv), deadline_ms=args.deadline_ms)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.out, index=False)
    print(f"wrote {len(result)} paired contrast rows to {args.out}")


if __name__ == "__main__":
    main()
