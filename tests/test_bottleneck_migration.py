import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import bottleneck_migration as bm  # noqa: E402
import deadline_metrics as dm  # noqa: E402


def test_paired_contrast_identifies_wireless_dominance():
    # Scheduled cells improve miss rate by 0.20; TAS improves it by only 0.05.
    cell_rate = {1: 0.40, 2: 0.20, 3: 0.38, 4: 0.18, 5: 0.35, 6: 0.15}
    rows = []
    for rep in range(3):
        for cell, rate in cell_rate.items():
            row = {
                "cell": cell, "class": "state", "N_AMR": 40,
                "lambda_tel_Mbps": 95.0, "phy_rate_Mbps": 54, "rep": rep,
            }
            row.update({f"miss_B_{deadline}ms": rate for deadline in dm.D_SPECTRUM_MS})
            rows.append(row)
    result = bm.build_contrasts(pd.DataFrame(rows)).iloc[0]
    assert result["wireless_gain"] == pytest.approx(0.20)
    assert result["wired_fifo_to_tas_gain"] == pytest.approx(0.05)
    assert result["dominant_bottleneck"] == "wireless"


def test_uncongested_vs_saturated_tie_and_deadline_override():
    import numpy as np
    import pandas as pd
    import bottleneck_migration as bm
    import deadline_metrics as dm

    rows = []
    for n_amr, base_miss in [(5, 0.0), (80, 1.0)]:
        for cell in range(1, 7):
            for rep in range(3):
                row = {
                    "cell": cell,
                    "class": "state",
                    "N_AMR": n_amr,
                    "lambda_tel_Mbps": 22.4,
                    "phy_rate_Mbps": 54,
                    "rep": rep,
                }
                for d in dm.D_SPECTRUM_MS:
                    # At d=10ms, make Cell 1..6 show a wired bottleneck for N_AMR=5
                    if d == 10 and n_amr == 5:
                        row[f"miss_B_{d}ms"] = 0.40 if cell in (1, 2) else 0.0
                    else:
                        row[f"miss_B_{d}ms"] = base_miss
                rows.append(row)

    df = pd.DataFrame(rows)
    out_nom = bm.build_contrasts(df).set_index("N_AMR")
    assert out_nom.loc[5, "dominant_bottleneck"] == "none_or_uncongested"
    assert out_nom.loc[80, "dominant_bottleneck"] == "mixed_or_uncertain"

    out_10ms = bm.build_contrasts(df, deadline_ms=10).set_index("N_AMR")
    assert out_10ms.loc[5, "dominant_bottleneck"] == "wired"
    assert np.isclose(out_10ms.loc[5, "wired_fifo_to_tas_gain"], 0.40)
