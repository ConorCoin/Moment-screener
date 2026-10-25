"""Grid search over stop/target %, long-only (shorts dropped per findings), with a proper
in-sample / out-of-sample split so we're not just curve-fitting to one historical window.

LOCAL ANALYSIS ONLY — not part of the live pipeline, not pushed to the repo.

Methodology: the walk-forward simulation is run once per (stop, target) combination over the
full available history (indicators always use only past data, no lookahead). Trades and daily
returns are then split by date into:
  - IN-SAMPLE   (before SPLIT_DATE): used to pick the best-looking configuration.
  - OUT-OF-SAMPLE (on/after SPLIT_DATE): held out, never used for selection, only to check
    whether the in-sample winner's edge actually held up on unseen data.
"""

import numpy as np
import pandas as pd

import backtest
import config
import universe

SPLIT_DATE = pd.Timestamp("2023-01-01")

STOPS = [0.04, 0.05, 0.07]
TARGETS = [0.08, 0.10, 0.12, 0.15]


def _split_stats(returns: pd.Series, trades: pd.DataFrame, split_date: pd.Timestamp):
    is_returns = returns[returns.index < split_date]
    oos_returns = returns[returns.index >= split_date]
    is_trades = trades[trades["entry_date"] < split_date] if not trades.empty else trades
    oos_trades = trades[trades["entry_date"] >= split_date] if not trades.empty else trades
    return (
        backtest._stats(is_returns), is_trades,
        backtest._stats(oos_returns) if len(oos_returns) else None, oos_trades,
    )


def main():
    uni = universe.build_universe()
    print("Building indicator frames once (reused across the whole grid)...")
    wide, ticker_sector, sector_rs, dates = backtest._build_wide_frames(uni)

    rows = []
    cache = {}  # (stop, target) -> (returns, trades)
    for stop in STOPS:
        for target in TARGETS:
            returns, trades, _ = backtest.simulate(
                wide, ticker_sector, sector_rs, dates,
                stop_pct=stop, target_pct=target, include_short=False,
            )
            cache[(stop, target)] = (returns, trades)
            is_stats, is_trades, oos_stats, oos_trades = _split_stats(returns, trades, SPLIT_DATE)
            rows.append({
                "stop": stop, "target": target,
                "is_trades": len(is_trades), "is_win_rate": (is_trades["return"] > 0).mean() if len(is_trades) else float("nan"),
                "is_cagr": is_stats["cagr"], "is_sharpe": is_stats["sharpe"], "is_maxdd": is_stats["max_drawdown"],
                "oos_trades": len(oos_trades), "oos_win_rate": (oos_trades["return"] > 0).mean() if len(oos_trades) else float("nan"),
                "oos_cagr": oos_stats["cagr"] if oos_stats else float("nan"),
                "oos_sharpe": oos_stats["sharpe"] if oos_stats else float("nan"),
                "oos_maxdd": oos_stats["max_drawdown"] if oos_stats else float("nan"),
            })
            print(f"  stop={stop:.0%} target={target:.0%}: "
                  f"IS CAGR {is_stats['cagr']:.1%} Sharpe {is_stats['sharpe']:.2f} | "
                  f"OOS CAGR {oos_stats['cagr']:.1%} Sharpe {oos_stats['sharpe']:.2f}" if oos_stats else "OOS: n/a")

    results = pd.DataFrame(rows).sort_values("is_sharpe", ascending=False)
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")

    print("\n=== Ranked by IN-SAMPLE Sharpe (selection period, pre-2023) ===")
    print(results.to_string(index=False))

    best = results.iloc[0]
    print(f"\n=== Best in-sample config: stop={best['stop']:.0%} target={best['target']:.0%} ===")
    print(f"In-sample:     CAGR {best['is_cagr']:.1%}  Sharpe {best['is_sharpe']:.2f}  "
          f"MaxDD {best['is_maxdd']:.1%}  ({int(best['is_trades'])} trades, {best['is_win_rate']:.1%} win rate)")
    print(f"Out-of-sample: CAGR {best['oos_cagr']:.1%}  Sharpe {best['oos_sharpe']:.2f}  "
          f"MaxDD {best['oos_maxdd']:.1%}  ({int(best['oos_trades'])} trades, {best['oos_win_rate']:.1%} win rate)")

    # Benchmark comparison over the same two sub-periods
    full_returns, _ = cache[(best["stop"], best["target"])]
    spy = backtest._buy_hold_equity(config.BENCHMARK, full_returns.index[0], full_returns.index)
    spy_is = backtest._stats(spy[spy.index < SPLIT_DATE])
    spy_oos = backtest._stats(spy[spy.index >= SPLIT_DATE])
    print(f"\nSPY buy-hold:  IS CAGR {spy_is['cagr']:.1%} Sharpe {spy_is['sharpe']:.2f}  |  "
          f"OOS CAGR {spy_oos['cagr']:.1%} Sharpe {spy_oos['sharpe']:.2f}")

    results.to_csv("tune_grid_results.csv", index=False)
    print("\nSaved: tune_grid_results.csv (local only, not pushed)")


if __name__ == "__main__":
    main()
