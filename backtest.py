"""Walk-forward backtest of the sector-rotation + momentum screener.

LOCAL ANALYSIS ONLY — not part of the live pipeline, not pushed to the repo.

Key assumptions / simplifications (read before trusting the numbers):
- Long signals: simulated as straight long-stock P&L.
- Short signals: simulated as straight short-stock P&L (symmetric % return). This is NOT
  what a real put/put-spread position would have returned — real options underperform this
  due to time decay (theta) and have a defined-risk payoff shape. This only tests whether
  the *directional thesis* was right, not realistic short P&L.
- Entry fill: the trading day's Open, the session AFTER a trigger (matches "act next session").
- Exit fill: the stop or target price itself, the first day price touches it intraday
  (optimistic vs. real slippage/gaps; if both stop and target are touched the same day,
  the stop is assumed to hit first — conservative tie-break).
- No commissions, spread, or slippage modeled at all.
- Equal-weight sizing (1 / MAX_CONCURRENT per trade, capped at MAX_CONCURRENT open positions)
  is used ONLY to build an illustrative portfolio equity curve for comparison against
  buy-and-hold SPY/MTUM. This is not a position-sizing recommendation — that was explicitly
  deferred in the live build.
- Walk-forward / no lookahead: every indicator at date t uses only data up to and including t.
"""

import numpy as np
import pandas as pd

import config
import data
import universe

MAX_CONCURRENT = 20


def _indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    ma_fast = close.rolling(config.MA_FAST).mean()
    ma_slow = close.rolling(config.MA_SLOW).mean()
    ma_fast_slope = ma_fast - ma_fast.shift(config.MA_SLOPE_LOOKBACK)
    ma_slow_slope = ma_slow - ma_slow.shift(config.MA_SLOPE_LOOKBACK)
    momentum = close.shift(config.MOM_SKIP) / close.shift(config.MOM_LOOKBACK) - 1

    up = (close > ma_fast) & (ma_fast > ma_slow) & (ma_fast_slope > 0) & (ma_slow_slope > 0)
    down = (close < ma_fast) & (ma_fast < ma_slow) & (ma_fast_slope < 0) & (ma_slow_slope < 0)

    band = config.PULLBACK_BAND_PCT
    prev_close, prev_ma_fast = close.shift(1), ma_fast.shift(1)
    approached_up = ((prev_close - prev_ma_fast).abs() / prev_ma_fast <= band) | (prev_close <= prev_ma_fast)
    approached_down = ((prev_close - prev_ma_fast).abs() / prev_ma_fast <= band) | (prev_close >= prev_ma_fast)
    trigger_up = (up & approached_up & (close > ma_fast)).fillna(False)
    trigger_down = (down & approached_down & (close < ma_fast)).fillna(False)

    return pd.DataFrame(
        {
            "Open": df["Open"], "High": df["High"], "Low": df["Low"], "Close": close,
            "trend_up": up.fillna(False), "trend_down": down.fillna(False),
            "momentum": momentum,
            "trigger_up": trigger_up, "trigger_down": trigger_down,
        }
    )


def _build_wide_frames(uni: pd.DataFrame):
    bench = data.load_prices(config.BENCHMARK)
    master_dates = bench.index

    fields = ["Open", "High", "Low", "Close", "trend_up", "trend_down", "momentum", "trigger_up", "trigger_down"]
    wide = {f: {} for f in fields}
    ticker_sector = {}

    tickers = uni["ticker"].tolist()
    for t in tickers:
        df = data.load_prices(t)
        if df is None or len(df) <= config.MOM_LOOKBACK:
            continue
        ind = _indicator_frame(df).reindex(master_dates)
        for f in fields:
            wide[f][t] = ind[f]
        ticker_sector[t] = uni.loc[uni["ticker"] == t, "sector_etf"].iloc[0]

    wide_frames = {f: pd.DataFrame(wide[f]) for f in fields}
    ticker_sector = pd.Series(ticker_sector)

    # Sector relative strength vs SPY, full time series
    w1, w2 = config.SECTOR_RS_WINDOWS
    spy_close = bench["Close"].reindex(master_dates)
    spy_ret1 = spy_close / spy_close.shift(w1) - 1
    spy_ret2 = spy_close / spy_close.shift(w2) - 1

    rs = {}
    for etf in config.SECTOR_ETFS:
        edf = data.load_prices(etf)
        if edf is None:
            continue
        c = edf["Close"].reindex(master_dates)
        r1 = c / c.shift(w1) - 1
        r2 = c / c.shift(w2) - 1
        rs[etf] = 0.5 * (r1 - spy_ret1) + 0.5 * (r2 - spy_ret2)
    sector_rs = pd.DataFrame(rs)

    return wide_frames, ticker_sector, sector_rs, master_dates


def simulate(wide, ticker_sector, sector_rs, dates, stop_pct, target_pct,
             include_short=True, max_concurrent=MAX_CONCURRENT):
    """Runs the walk-forward simulation with the given exit/direction parameters.
    Reuses precomputed indicator frames so a parameter grid doesn't recompute them each time."""
    open_df, high_df, low_df, close_df = wide["Open"], wide["High"], wide["Low"], wide["Close"]
    trend_up_df, trend_down_df = wide["trend_up"], wide["trend_down"]
    momentum_df = wide["momentum"]
    trigger_up_df, trigger_down_df = wide["trigger_up"], wide["trigger_down"]

    # Warm-up: skip until enough history exists for momentum + sector rs to be mostly populated.
    warmup = max(config.MOM_LOOKBACK + config.MOM_SKIP, max(config.SECTOR_RS_WINDOWS)) + 5
    sim_dates = dates[warmup:]

    positions = {}  # ticker -> dict(direction, stop, target, prev_price)
    pending = []    # list of (ticker, direction) to fill at next Open
    trades = []
    daily_returns = []
    equity_dates = []

    for date in sim_dates:
        slot_returns = []

        # 1. Fill pending entries at today's Open
        still_pending = []
        for ticker, direction in pending:
            if ticker in positions or len(positions) >= MAX_CONCURRENT:
                continue
            o = open_df.at[date, ticker] if ticker in open_df.columns else np.nan
            if pd.isna(o):
                continue
            if direction == "up":
                stop, target = o * (1 - stop_pct), o * (1 + target_pct)
            else:
                stop, target = o * (1 + stop_pct), o * (1 - target_pct)
            positions[ticker] = {"direction": direction, "entry_date": date, "entry_price": o,
                                 "stop": stop, "target": target, "prev_price": o}
        pending = still_pending  # anything skipped (capacity/no data) is dropped, not retried

        # 2. Check stop/target on all open positions using today's H/L; else mark-to-close
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            h = high_df.at[date, ticker] if ticker in high_df.columns else np.nan
            l = low_df.at[date, ticker] if ticker in low_df.columns else np.nan
            c = close_df.at[date, ticker] if ticker in close_df.columns else np.nan
            if pd.isna(h) or pd.isna(l) or pd.isna(c):
                slot_returns.append(0.0)  # data gap: hold flat for the day
                continue

            exit_price = None
            if pos["direction"] == "up":
                if l <= pos["stop"]:
                    exit_price = pos["stop"]
                elif h >= pos["target"]:
                    exit_price = pos["target"]
            else:
                if h >= pos["stop"]:
                    exit_price = pos["stop"]
                elif l <= pos["target"]:
                    exit_price = pos["target"]

            if exit_price is not None:
                ret = exit_price / pos["prev_price"] - 1
                if pos["direction"] == "down":
                    ret = -ret
                slot_returns.append(ret)
                trade_ret = exit_price / pos["entry_price"] - 1
                if pos["direction"] == "down":
                    trade_ret = -trade_ret
                trades.append({
                    "ticker": ticker, "direction": pos["direction"],
                    "entry_date": pos["entry_date"], "exit_date": date,
                    "entry_price": pos["entry_price"], "exit_price": exit_price,
                    "return": trade_ret, "hit": "target" if trade_ret > 0 else "stop",
                })
                del positions[ticker]
            else:
                ret = c / pos["prev_price"] - 1
                if pos["direction"] == "down":
                    ret = -ret
                slot_returns.append(ret)
                pos["prev_price"] = c

        # Pad/trim to MAX_CONCURRENT slots (idle slots = 0% that day = cash)
        while len(slot_returns) < max_concurrent:
            slot_returns.append(0.0)
        daily_returns.append(float(np.mean(slot_returns[:max_concurrent])))
        equity_dates.append(date)

        # 3. Scan for new signals today -> enter next session
        rs_today = sector_rs.loc[date].dropna()
        if len(rs_today) >= 2:
            ranked = rs_today.sort_values(ascending=False)
            leading = set(ranked.head(config.N_LEADING_SECTORS).index)
            lagging = set(ranked.tail(config.N_LAGGING_SECTORS).index)
        else:
            leading, lagging = set(), set()

        sector_aligned = ticker_sector.reindex(trend_up_df.columns)

        up_today = trend_up_df.loc[date] & sector_aligned.isin(leading)
        cand_long = momentum_df.loc[date][up_today].dropna().sort_values(ascending=False)
        n_long = max(1, int(len(cand_long) * config.TOP_DECILE)) if len(cand_long) else 0
        top_long = cand_long.head(n_long).index
        new_pending = [(t, "up") for t in top_long if trigger_up_df.at[date, t] and t not in positions]

        if include_short:
            down_today = trend_down_df.loc[date] & sector_aligned.isin(lagging)
            cand_short = momentum_df.loc[date][down_today].dropna().sort_values(ascending=True)
            n_short = max(1, int(len(cand_short) * config.TOP_DECILE)) if len(cand_short) else 0
            top_short = cand_short.head(n_short).index
            new_pending += [(t, "down") for t in top_short if trigger_down_df.at[date, t] and t not in positions]

        pending = new_pending

    # Force-close anything still open at the end, mark-to-last-close
    last_date = sim_dates[-1]
    for ticker, pos in positions.items():
        c = close_df.at[last_date, ticker] if ticker in close_df.columns else pos["entry_price"]
        trade_ret = c / pos["entry_price"] - 1
        if pos["direction"] == "down":
            trade_ret = -trade_ret
        trades.append({
            "ticker": ticker, "direction": pos["direction"], "entry_date": pos["entry_date"],
            "exit_date": last_date, "entry_price": pos["entry_price"], "exit_price": c,
            "return": trade_ret, "hit": "open_at_end",
        })

    equity = pd.Series(daily_returns, index=equity_dates)
    trades_df = pd.DataFrame(trades)
    return equity, trades_df, sim_dates[0]


def run_backtest():
    """Convenience wrapper: builds frames fresh and runs with config.py's default params."""
    uni = universe.build_universe()
    wide, ticker_sector, sector_rs, dates = _build_wide_frames(uni)
    return simulate(wide, ticker_sector, sector_rs, dates,
                     stop_pct=config.STOP_LOSS_PCT, target_pct=config.PROFIT_TARGET_PCT,
                     include_short=True)


def _buy_hold_equity(ticker: str, start_date, dates) -> pd.Series:
    df = data.load_prices(ticker)
    c = df["Close"].reindex(dates)
    c = c.loc[c.first_valid_index():]
    rets = c.pct_change().fillna(0)
    return rets.loc[rets.index >= start_date]


def _stats(returns: pd.Series) -> dict:
    equity_curve = (1 + returns).cumprod()
    total_return = equity_curve.iloc[-1] - 1
    n_years = len(returns) / 252
    cagr = (equity_curve.iloc[-1]) ** (1 / n_years) - 1 if n_years > 0 else float("nan")
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else float("nan")
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    max_dd = drawdown.min()
    return {"total_return": total_return, "cagr": cagr, "sharpe": sharpe, "max_drawdown": max_dd}


if __name__ == "__main__":
    print("Running backtest (this uses full history, no lookahead)...")
    strat_returns, trades_df, start_date = run_backtest()
    print(f"Backtest window: {start_date.date()} to {strat_returns.index[-1].date()} "
          f"({len(strat_returns)} trading days)\n")

    print(f"=== Trades: {len(trades_df)} ===")
    if not trades_df.empty:
        for direction in ("up", "down"):
            sub = trades_df[trades_df["direction"] == direction]
            if sub.empty:
                print(f"{direction.upper()}: no trades")
                continue
            win_rate = (sub["return"] > 0).mean()
            print(f"{direction.upper()}: {len(sub)} trades, win rate {win_rate:.1%}, "
                  f"avg return {sub['return'].mean():.2%}, "
                  f"avg win {sub[sub['return']>0]['return'].mean():.2%}, "
                  f"avg loss {sub[sub['return']<=0]['return'].mean():.2%}")
        print(f"\nALL: win rate {(trades_df['return']>0).mean():.1%}, "
              f"avg return/trade {trades_df['return'].mean():.2%}, "
              f"expectancy (sum of all trade returns / trades) {trades_df['return'].sum()/len(trades_df):.2%}")

    print("\n=== Portfolio-level (equal-weight, illustrative only) ===")
    strat_stats = _stats(strat_returns)
    spy_returns = _buy_hold_equity(config.BENCHMARK, start_date, strat_returns.index)
    mtum_returns = _buy_hold_equity("MTUM", start_date, strat_returns.index)
    spy_stats = _stats(spy_returns.reindex(strat_returns.index).fillna(0))
    mtum_stats = _stats(mtum_returns.reindex(strat_returns.index).fillna(0))

    for name, stats in (("Strategy", strat_stats), ("SPY buy-hold", spy_stats), ("MTUM buy-hold", mtum_stats)):
        print(f"{name:15s} total return {stats['total_return']:7.1%}  CAGR {stats['cagr']:6.1%}  "
              f"Sharpe {stats['sharpe']:5.2f}  Max DD {stats['max_drawdown']:7.1%}")

    trades_df.to_csv("backtest_trades.csv", index=False)
    strat_returns.to_csv("backtest_daily_returns.csv")
    print("\nSaved: backtest_trades.csv, backtest_daily_returns.csv (local only, not pushed)")
