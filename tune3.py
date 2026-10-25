"""Round 3: five levers aimed at reducing how often trades hit the stop, tested as a full
factorial design (32 combinations) on top of the round-2 best config, with the same
in-sample/out-of-sample discipline as before.

LOCAL ANALYSIS ONLY — not part of the live pipeline, not pushed to the repo.

Factors (each on/off):
  A: ATR-based stop/target sizing (2x/3x each stock's own ATR) vs flat 7%/10% off entry
  B: 2-day entry confirmation (reclaim must hold 2 closes) vs single-day reclaim
  C: volume confirmation (entry day's volume above its own 20-day average) vs none
  D: minimum trend slope (MA slope must exceed 1% of the MA's own level) vs any positive slope
  E: trailing stop (ratchets with favorable price action, never loosens) vs fixed stop

Base config (held fixed, from config.py / round 2): long-only, 7% stop / 10% target (used
when stop_mode="pct"), 20% top-decile candidate pool, 5 leading sectors, 6-1 month momentum.

Methodology: A, B, C, D change the indicator frames themselves, so each of their 16
combinations needs a fresh _build_wide_frames() call. E (trailing stop) only changes the
simulate() loop, so it's tested on top of each of those 16 without rebuilding frames —
16 rebuilds x 2 (trailing on/off) = 32 total simulation runs.
"""

import itertools

import pandas as pd

import backtest
import config
import universe

SPLIT_DATE = pd.Timestamp("2023-01-01")
STOP, TARGET = config.STOP_LOSS_PCT, config.PROFIT_TARGET_PCT
ATR_STOP_MULT, ATR_TARGET_MULT = 2.0, 3.0


def _split_eval(returns, trades):
    is_r = returns[returns.index < SPLIT_DATE]
    oos_r = returns[returns.index >= SPLIT_DATE]
    is_t = trades[trades["entry_date"] < SPLIT_DATE] if not trades.empty else trades
    oos_t = trades[trades["entry_date"] >= SPLIT_DATE] if not trades.empty else trades
    is_stats = backtest._stats(is_r)
    oos_stats = backtest._stats(oos_r) if len(oos_r) else None
    return {
        "is_trades": len(is_t),
        "is_win_rate": (is_t["return"] > 0).mean() if len(is_t) else float("nan"),
        "is_stop_rate": (is_t["hit"] == "stop").mean() if len(is_t) else float("nan"),
        "is_cagr": is_stats["cagr"], "is_sharpe": is_stats["sharpe"],
        "oos_trades": len(oos_t),
        "oos_win_rate": (oos_t["return"] > 0).mean() if len(oos_t) else float("nan"),
        "oos_stop_rate": (oos_t["hit"] == "stop").mean() if len(oos_t) else float("nan"),
        "oos_cagr": oos_stats["cagr"] if oos_stats else float("nan"),
        "oos_sharpe": oos_stats["sharpe"] if oos_stats else float("nan"),
    }


def main():
    uni = universe.build_universe()
    rows = []

    combos = list(itertools.product([False, True], repeat=4))  # (A, B, C, D)
    for i, (use_atr, confirm2, volconfirm, slopefilter) in enumerate(combos):
        confirm_days = 2 if confirm2 else 1
        min_slope = 0.01 if slopefilter else 0.0
        print(f"[{i+1}/16] Building frames: ATR={use_atr} confirm2={confirm2} "
              f"vol={volconfirm} slope={slopefilter}", flush=True)
        wide, ts, sr, dates = backtest._build_wide_frames(
            uni, confirm_days=confirm_days, require_volume=volconfirm, min_slope_pct=min_slope
        )
        for trailing in (False, True):
            stop_mode = "atr" if use_atr else "pct"
            returns, trades, _ = backtest.simulate(
                wide, ts, sr, dates, stop_pct=STOP, target_pct=TARGET, include_short=False,
                stop_mode=stop_mode, atr_stop_mult=ATR_STOP_MULT, atr_target_mult=ATR_TARGET_MULT,
                trailing_stop=trailing,
            )
            row = {"A_atr": use_atr, "B_confirm2": confirm2, "C_volume": volconfirm,
                   "D_slope": slopefilter, "E_trailing": trailing}
            row.update(_split_eval(returns, trades))
            rows.append(row)
            print(f"    trailing={trailing}: {row['is_trades']} IS trades, "
                  f"IS Sharpe {row['is_sharpe']:.2f} stop-rate {row['is_stop_rate']:.1%} | "
                  f"OOS Sharpe {row['oos_sharpe']:.2f} stop-rate {row['oos_stop_rate']:.1%}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv("tune3_factorial.csv", index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")

    print("\n=== Full results, ranked by in-sample Sharpe ===")
    print(df.sort_values("is_sharpe", ascending=False).to_string(index=False))

    print("\n=== Main effects: avg Sharpe / stop-rate when each factor is ON vs OFF "
          "(averaged across all other factor settings) ===")
    for factor in ["A_atr", "B_confirm2", "C_volume", "D_slope", "E_trailing"]:
        on, off = df[df[factor]], df[~df[factor]]
        print(f"{factor:12s}: IS Sharpe ON {on['is_sharpe'].mean():6.3f}  OFF {off['is_sharpe'].mean():6.3f}  |  "
              f"OOS Sharpe ON {on['oos_sharpe'].mean():6.3f}  OFF {off['oos_sharpe'].mean():6.3f}  |  "
              f"IS stop-rate ON {on['is_stop_rate'].mean():.1%}  OFF {off['is_stop_rate'].mean():.1%}")

    print("\nSaved: tune3_factorial.csv (local only, not pushed)")


if __name__ == "__main__":
    main()
