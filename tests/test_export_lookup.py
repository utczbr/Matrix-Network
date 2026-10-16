import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deadline_metrics as dm  # noqa: E402
import export_lookup as ex  # noqa: E402

NS = (5, 10)
LAMS = (22.4, 74.7, 110.0, 149.3)


def synthetic_packets(cells=(1, 3), classes=("state", "orders"), reps=3, per_rep=4000, seed=3):
    """Synthetic per-packet table; delay and loss grow with N and lambda (monotone, for PCHIP checks)."""
    rng = np.random.default_rng(seed)
    frames = []
    for cell in cells:
        for cls in classes:
            for n in NS:
                for lam in LAMS:
                    for rep in range(reps):
                        g = np.sort(rng.uniform(0.0, 60.0, per_rep))
                        scale = 0.0005 * (1 + n / 5) * (1 + lam / 40)            # seconds
                        a = g + 0.0002 + rng.exponential(scale, per_rep)
                        cause = np.full(per_rep, "", dtype=object)
                        lost = rng.random(per_rep) < 0.002 * (lam / 22.4)
                        a[lost] = np.nan
                        cause[lost] = rng.choice(["queue", "retry"], lost.sum())
                        frames.append(pd.DataFrame({
                            "cell": cell, "class": cls, "N_AMR": n, "lambda_tel_Mbps": lam,
                            "phy_rate_Mbps": 54, "rep": rep, "g_s": g, "a_s": a, "drop_cause": cause}))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def tables():
    pk = synthetic_packets()
    summary, ecdf = ex.build_tables(pk)
    return pk, summary, ecdf


def test_schema_columns_and_row_counts(tables):
    _, summary, ecdf = tables
    assert list(summary.columns) == ex.SUMMARY_COLUMNS
    assert list(ecdf.columns) == ex.ECDF_COLUMNS
    assert len(summary) == 2 * 2 * len(NS) * len(LAMS)
    assert (ecdf.groupby(ex.KEY).size() == 25).all()
    assert sorted(ecdf["quantile_level"].unique()) == list(dm.QUANTILE_LEVELS)
    assert (summary["schema_version"] == ex.SCHEMA_VERSION).all()


def test_p_loss_counts_physical_drops_only(tables):
    pk, summary, _ = tables
    row = summary.iloc[0]
    sub = pk[(pk[ex.KEY] == row[ex.KEY].values).all(axis=1)]
    g, a = sub["g_s"].to_numpy(), sub["a_s"].to_numpy()
    nominal = dm.NOMINAL_D_MS[row["class"]]
    n_drops = row["n_Drop_Queue"] + row["n_Drop_Retry"] + row["n_Drop_Other"]
    assert row["p_loss"] == pytest.approx(n_drops / row["n_total"])
    assert row["n_Drop_Other"] == 0
    # delivered-but-late packets are not losses: miss_A >= p_loss at every D
    for d in dm.D_SPECTRUM_MS:
        assert row[f"miss_A_{d}ms"] >= row["p_loss"] - 1e-12
    assert row["n_reps"] == 3 and nominal in dm.D_SPECTRUM_MS


def test_miss_rates_are_monotone_in_d_and_b_not_above_a(tables):
    _, summary, _ = tables
    for d1, d2 in zip(dm.D_SPECTRUM_MS[:-1], dm.D_SPECTRUM_MS[1:]):
        assert (summary[f"miss_A_{d2}ms"] <= summary[f"miss_A_{d1}ms"] + 1e-12).all()
    # Miss_B <= Miss_A holds per packet, and all columns share one packet set
    for d in dm.D_SPECTRUM_MS:
        assert (summary[f"miss_B_{d}ms"] <= summary[f"miss_A_{d}ms"] + 1e-12).all()


def test_ecdf_is_non_decreasing_and_percentiles_match(tables):
    _, summary, ecdf = tables
    for _, grp in ecdf.groupby(ex.KEY):
        assert (grp.sort_values("quantile_level")["delay_ms"].diff().dropna() >= 0).all()
    k = summary.iloc[0]
    e = ecdf[(ecdf[ex.KEY] == k[ex.KEY].values).all(axis=1)].set_index("quantile_level")["delay_ms"]
    assert k["lat_p50"] == e[0.50] and k["lat_p99"] == e[0.99] and k["lat_p99_9"] == e[0.999]


def test_tail_flag(tables):
    _, summary, _ = tables
    assert (summary["flag_p99"] == "OK").all()
    assert (summary["flag_p99_9"] == "INSUFFICIENT_TAIL_SAMPLES").all()


def test_phase_is_shared_across_cells_for_paired_comparison(tables):
    _, summary, _ = tables
    a = summary[(summary.cell == 1) & (summary["class"] == "state")]
    assert len(a) == len(NS) * len(LAMS)                       # sanity; phi equality is tested in the metrics suite


def test_write_tables_csv_json_mirror(tables, tmp_path):
    _, summary, ecdf = tables
    ex.write_tables(summary, ecdf, tmp_path)
    s_csv = pd.read_csv(tmp_path / "lookup_summary.csv")
    assert set(s_csv["flag_p99"]) == {"OK"}
    assert set(s_csv["flag_p99_9"]) == {"INSUFFICIENT_TAIL_SAMPLES"}
    s_json = json.loads((tmp_path / "lookup_summary.json").read_text())
    e_json = json.loads((tmp_path / "lookup_ecdf.json").read_text())
    assert len(s_json) == len(summary) and len(e_json) == len(ecdf)
    assert s_json[0]["flag_p99_9"] == "INSUFFICIENT_TAIL_SAMPLES"
    e_csv = pd.read_csv(tmp_path / "lookup_ecdf.csv")
    assert np.allclose(e_csv["delay_ms"], ecdf["delay_ms"])


def test_all_lost_key_has_no_ecdf_rows_and_p_loss_one():
    pk = synthetic_packets(cells=(1,), classes=("state",), reps=2, per_rep=500)
    pk = pk[(pk.N_AMR == 5) & (pk.lambda_tel_Mbps == 22.4)].copy()
    pk["a_s"] = np.nan
    pk["drop_cause"] = "queue"
    summary, ecdf = ex.build_tables(pk)
    assert ecdf.empty and summary["p_loss"].iloc[0] == 1.0 and np.isnan(summary["lat_p50"].iloc[0])


# ---- interpolation (section 5.4)
def test_interpolation_reproduces_grid_nodes(tables):
    _, summary, ecdf = tables
    r = ex.interpolate(summary, ecdf, cell=1, cls="state", phy_rate=54, n_amr=10, lam=74.7)
    e = ecdf[(ecdf.cell == 1) & (ecdf["class"] == "state") & (ecdf.N_AMR == 10) & (ecdf.lambda_tel_Mbps == 74.7)]
    assert np.allclose(r["delay_ms"], e.sort_values("quantile_level")["delay_ms"])


def test_interpolation_is_monotone_between_nodes_and_non_crossing(tables):
    _, summary, ecdf = tables
    prev = None
    for lam in (22.4, 30, 40, 50, 60, 74.7):                   # below the FIFO saturation region
        r = ex.interpolate(summary, ecdf, cell=3, cls="state", phy_rate=54, n_amr=7.5, lam=lam)
        assert (np.diff(r["delay_ms"]) >= 0).all() and (r["delay_ms"] >= 0).all()
        if prev is not None:
            assert (r["delay_ms"][4:] >= prev[4:] - 1e-9).all()   # q >= 0.25; lowest levels are sampling noise
        prev = r["delay_ms"]


def test_out_of_grid_is_clamped_with_warning(tables, caplog):
    _, summary, ecdf = tables
    with caplog.at_level(logging.WARNING):
        hi = ex.interpolate(summary, ecdf, cell=3, cls="state", phy_rate=54, n_amr=80, lam=200)
    edge = ex.interpolate(summary, ecdf, cell=3, cls="state", phy_rate=54, n_amr=10, lam=149.3)
    assert np.allclose(hi["delay_ms"], edge["delay_ms"])
    assert sum("outside grid" in m for m in caplog.messages) == 2


def test_saturation_clamp_is_nearest_neighbour_for_fifo_only(tables):
    _, summary, ecdf = tables
    kw = dict(cls="state", phy_rate=54, n_amr=10, lam=120.0)
    fifo = ex.interpolate(summary, ecdf, cell=1, **kw)          # lambda > 100: snaps to 110
    node = ex.interpolate(summary, ecdf, cell=1, cls="state", phy_rate=54, n_amr=10, lam=110.0)
    prio = ex.interpolate(summary, ecdf, cell=3, **kw)          # priority cell: plain PCHIP
    assert np.allclose(fifo["delay_ms"], node["delay_ms"])
    assert not np.allclose(prio["delay_ms"], ex.interpolate(summary, ecdf, cell=3, cls="state", phy_rate=54,
                                                            n_amr=10, lam=110.0)["delay_ms"])


def test_unknown_key_raises(tables):
    _, summary, ecdf = tables
    with pytest.raises(KeyError):
        ex.interpolate(summary, ecdf, cell=6, cls="state", phy_rate=54, n_amr=10, lam=22.4)


def test_cli_sample_prototype(tmp_path):
    pk = synthetic_packets(cells=(1,), classes=("state",), reps=2, per_rep=800)
    csv = tmp_path / "packets.csv"
    pk.to_csv(csv, index=False)
    ex.main(["--packets", str(csv), "--out-dir", str(tmp_path / "out"), "--sample", "1,10,74.7,54"])
    s = pd.read_csv(tmp_path / "out" / "lookup_summary.csv")
    e = pd.read_csv(tmp_path / "out" / "lookup_ecdf.csv")
    assert len(s) == 1 and len(e) == 25
