"""Core screening logic: trend filter, momentum ranking, pullback entry trigger, stop/target levels."""

import pandas as pd

import config
import data
import sector
import universe


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ma_fast"] = df["Close"].rolling(config.MA_FAST).mean()
    df["ma_slow"] = df["Close"].rolling(config.MA_SLOW).mean()
    df["ma_fast_slope"] = df["ma_fast"] - df["ma_fast"].shift(config.MA_SLOPE_LOOKBACK)
    df["ma_slow_slope"] = df["ma_slow"] - df["ma_slow"].shift(config.MA_SLOPE_LOOKBACK)
    return df


def _momentum_12_1(df: pd.DataFrame) -> float:
    closes = df["Close"].dropna()
    if len(closes) <= config.MOM_LOOKBACK:
        return float("nan")
    p_now = closes.iloc[-1 - config.MOM_SKIP]
    p_then = closes.iloc[-1 - config.MOM_LOOKBACK]
    return p_now / p_then - 1.0


def _trend_state(row) -> str:
    """'up' if confirmed uptrend, 'down' if confirmed downtrend, else None."""
    if pd.isna(row[["ma_fast", "ma_slow", "ma_fast_slope", "ma_slow_slope"]]).any():
        return None
    price = row["Close"]
    if price > row["ma_fast"] > row["ma_slow"] and row["ma_fast_slope"] > 0 and row["ma_slow_slope"] > 0:
        return "up"
    if price < row["ma_fast"] < row["ma_slow"] and row["ma_fast_slope"] < 0 and row["ma_slow_slope"] < 0:
        return "down"
    return None


def _entry_trigger(df: pd.DataFrame, direction: str) -> bool:
    """Checks the most recent bar for a pullback-to-50dma-then-reclaim trigger."""
    if len(df) < 2:
        return False
    today, yday = df.iloc[-1], df.iloc[-2]
    if pd.isna(today["ma_fast"]) or pd.isna(yday["ma_fast"]):
        return False

    band = config.PULLBACK_BAND_PCT
    if direction == "up":
        approached = abs(yday["Close"] - yday["ma_fast"]) / yday["ma_fast"] <= band or yday["Close"] <= yday["ma_fast"]
        reclaimed = today["Close"] > today["ma_fast"]
        return approached and reclaimed
    else:  # "down"
        approached = abs(yday["Close"] - yday["ma_fast"]) / yday["ma_fast"] <= band or yday["Close"] >= yday["ma_fast"]
        broke_down = today["Close"] < today["ma_fast"]
        return approached and broke_down


def _stop_target(entry_price: float, direction: str) -> tuple[float, float]:
    if direction == "up":
        stop = entry_price * (1 - config.STOP_LOSS_PCT)
        target = entry_price * (1 + config.PROFIT_TARGET_PCT)
    else:
        stop = entry_price * (1 + config.STOP_LOSS_PCT)
        target = entry_price * (1 - config.PROFIT_TARGET_PCT)
    return stop, target


def run_screen() -> dict:
    """Returns {'sectors': df, 'long_candidates': df, 'short_candidates': df,
    'long_triggers': df, 'short_triggers': df}."""
    uni = universe.build_universe()
    leading_etfs, lagging_etfs = sector.leading_lagging_etfs()
    sector_ranked = sector.rank_sectors()

    long_pool = uni[uni["sector_etf"].isin(leading_etfs)]["ticker"].tolist()
    short_pool = uni[uni["sector_etf"].isin(lagging_etfs)]["ticker"].tolist()

    long_rows, short_rows = [], []

    for direction, pool, bucket in (("up", long_pool, long_rows), ("down", short_pool, short_rows)):
        for ticker in pool:
            df = data.load_prices(ticker)
            if df is None or len(df) <= config.MOM_LOOKBACK:
                continue
            df = _compute_indicators(df)
            last = df.iloc[-1]
            state = _trend_state(last)
            if state != direction:
                continue
            mom = _momentum_12_1(df)
            if pd.isna(mom):
                continue
            triggered = _entry_trigger(df, direction)
            stop, target = _stop_target(last["Close"], direction)
            bucket.append(
                {
                    "ticker": ticker,
                    "sector_etf": uni.loc[uni["ticker"] == ticker, "sector_etf"].iloc[0],
                    "price": round(last["Close"], 2),
                    "momentum_12_1": mom,
                    "triggered_today": triggered,
                    "stop": round(stop, 2),
                    "target": round(target, 2),
                }
            )

    long_df = pd.DataFrame(long_rows)
    short_df = pd.DataFrame(short_rows)

    if not long_df.empty:
        long_df = long_df.sort_values("momentum_12_1", ascending=False)
        cutoff = max(1, int(len(long_df) * config.TOP_DECILE))
        long_df = long_df.head(cutoff)

    if not short_df.empty:
        short_df = short_df.sort_values("momentum_12_1", ascending=True)
        cutoff = max(1, int(len(short_df) * config.TOP_DECILE))
        short_df = short_df.head(cutoff)

    long_triggers = long_df[long_df["triggered_today"]] if not long_df.empty else long_df
    short_triggers = short_df[short_df["triggered_today"]] if not short_df.empty else short_df

    return {
        "sectors": sector_ranked,
        "long_candidates": long_df,
        "short_candidates": short_df,
        "long_triggers": long_triggers,
        "short_triggers": short_triggers,
    }


if __name__ == "__main__":
    results = run_screen()
    print("=== Sector ranking ===")
    print(results["sectors"][["etf", "sector", "rs_vs_spy"]].to_string(index=False))
    print(f"\n=== Long candidates (top decile, leading sectors): {len(results['long_candidates'])} ===")
    print(results["long_candidates"].to_string(index=False))
    print(f"\n=== Short candidates (bottom decile, lagging sectors): {len(results['short_candidates'])} ===")
    print(results["short_candidates"].to_string(index=False))
    print(f"\n=== LONG TRIGGERS TODAY: {len(results['long_triggers'])} ===")
    print(results["long_triggers"].to_string(index=False))
    print(f"\n=== SHORT TRIGGERS TODAY: {len(results['short_triggers'])} ===")
    print(results["short_triggers"].to_string(index=False))
