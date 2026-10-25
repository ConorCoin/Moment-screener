"""Ranks the 11 SPDR sector ETFs by relative strength vs. SPY."""

import pandas as pd

import config
import data


def _return_over(df: pd.DataFrame, days: int) -> float:
    closes = df["Close"].dropna()
    if len(closes) <= days:
        return float("nan")
    return closes.iloc[-1] / closes.iloc[-1 - days] - 1.0


def rank_sectors() -> pd.DataFrame:
    """Returns a DataFrame[etf, sector_name, ret_3m, ret_6m, rs_score] sorted best-to-worst."""
    bench_df = data.load_prices(config.BENCHMARK)
    if bench_df is None:
        raise RuntimeError(f"No price data cached for benchmark {config.BENCHMARK}; run data.py first.")

    w1, w2 = config.SECTOR_RS_WINDOWS
    bench_ret1 = _return_over(bench_df, w1)
    bench_ret2 = _return_over(bench_df, w2)

    rows = []
    for etf, name in config.SECTOR_ETFS.items():
        df = data.load_prices(etf)
        if df is None:
            continue
        r1 = _return_over(df, w1)
        r2 = _return_over(df, w2)
        rs1 = r1 - bench_ret1  # relative strength vs SPY over each window
        rs2 = r2 - bench_ret2
        rs_score = 0.5 * rs1 + 0.5 * rs2
        rows.append(
            {
                "etf": etf,
                "sector": name,
                f"ret_{w1}d": r1,
                f"ret_{w2}d": r2,
                "rs_vs_spy": rs_score,
            }
        )

    out = pd.DataFrame(rows).sort_values("rs_vs_spy", ascending=False).reset_index(drop=True)
    return out


def leading_lagging_etfs() -> tuple[list[str], list[str]]:
    ranked = rank_sectors()
    leading = ranked.head(config.N_LEADING_SECTORS)["etf"].tolist()
    lagging = ranked.tail(config.N_LAGGING_SECTORS)["etf"].tolist()
    return leading, lagging


if __name__ == "__main__":
    ranked = rank_sectors()
    pd.set_option("display.float_format", lambda x: f"{x:.2%}")
    print(ranked.to_string(index=False))
    lead, lag = leading_lagging_etfs()
    print(f"\nLeading sectors (long universe): {lead}")
    print(f"Lagging sectors (short universe): {lag}")
