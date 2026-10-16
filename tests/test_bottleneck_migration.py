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
