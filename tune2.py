"""Round 2 of tuning: candidate-pool breadth (TOP_DECILE, N_LEADING_SECTORS) and structural
indicator parameters (MA periods, momentum window, pullback band) — built on top of the
round-1 result (long-only, 7% stop / 10% target).

LOCAL ANALYSIS ONLY — not part of the live pipeline, not pushed to the repo.

Methodology, same discipline as round 1:
- IN-SAMPLE (before SPLIT_DATE) is used to pick a winner; OUT-OF-SAMPLE (on/after) is only
  ever read afterward, never used to choose.
- Phase A (TOP_DECILE x N_LEADING_SECTORS) only affects the day-by-day selection logic, so
  it reuses one set of precomputed indicator frames — cheap, a real grid.
- Phase B (MA_FAST/MA_SLOW, MOM_LOOKBACK/MOM_SKIP, PULLBACK_BAND_PCT) changes the indicators
  themselves, so each variant requires rebuilding the indicator frames from scratch. To avoid
  a combinatorial explosion (and the overfitting risk that comes with it), each structural
  variant is tested ONE AT A TIME against the Phase A winner, not crossed with each other.
"""

import pandas as pd

import backtest
import config
import universe

SPLIT_DATE = pd.Timestamp("2023-01-01")
STOP, TARGET = 0.07, 0.10  # validated round-1 result, held fixed throughout


def _split_eval(returns, trades):
    is_r = returns[returns.index < SPLIT_DATE]
    oos_r = returns[returns.index >= SPLIT_DATE]
    is_t = trades[trades["entry_date"] < SPLIT_DATE] if not trades.empty else trades
    oos_t = trades[trades["entry_date"] >= SPLIT_DATE] if not trades.empty else trades
    is_stats = backtest._stats(is_r)
    oos_stats = backtest._stats(oos_r) if len(oos_r) else None
    return {
        "is_trades": len(is_t), "is_win_rate": (is_t["return"] > 0).mean() if len(is_t) else float("nan"),
        "is_cagr": is_stats["cagr"], "is_sharpe": is_stats["sharpe"],
        "oos_trades": len(oos_t), "oos_win_rate": (oos_t["return"] > 0).mean() if len(oos_t) else float("nan"),
        "oos_cagr": oos_stats["cagr"] if oos_stats else float("nan"),
        "oos_sharpe": oos_stats["sharpe"] if oos_stats else float("nan"),
    }


def main():
    uni = universe.build_universe()
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")

    # ---------- Phase A: candidate pool breadth ----------
    print("=== Phase A: TOP_DECILE x N_LEADING_SECTORS (default MA/momentum/band) ===")
    wide, ticker_sector, sector_rs, dates = backtest._build_wide_frames(uni)

    rows_a = []
    orig_top_decile, orig_n_leading = config.TOP_DECILE, config.N_LEADING_SECTORS
    for td in (0.10, 0.15, 0.20):
        for nl in (3, 4, 5):
            config.TOP_DECILE, config.N_LEADING_SECTORS = td, nl
            returns, trades, _ = backtest.simulate(wide, ticker_sector, sector_rs, dates,
                                                     STOP, TARGET, include_short=False)
            row = {"top_decile": td, "n_leading": nl}
            row.update(_split_eval(returns, trades))
            rows_a.append(row)
            print(f"  top_decile={td:.0%} n_leading={nl}: "
                  f"IS Sharpe {row['is_sharpe']:.2f} CAGR {row['is_cagr']:.1%} | "
                  f"OOS Sharpe {row['oos_sharpe']:.2f} CAGR {row['oos_cagr']:.1%}")
    config.TOP_DECILE, config.N_LEADING_SECTORS = orig_top_decile, orig_n_leading

    df_a = pd.DataFrame(rows_a).sort_values("is_sharpe", ascending=False)
    print("\nRanked by in-sample Sharpe:")
    print(df_a.to_string(index=False))
    best_a = df_a.iloc[0]
    print(f"\nPhase A winner: top_decile={best_a['top_decile']:.0%}, n_leading={int(best_a['n_leading'])}")

    # Lock in Phase A winner for Phase B
    config.TOP_DECILE = best_a["top_decile"]
    config.N_LEADING_SECTORS = int(best_a["n_leading"])

    # ---------- Phase B: structural indicator parameters, one at a time ----------
    print("\n=== Phase B: structural variants (one change at a time vs Phase A winner) ===")
    baseline_row = {"label": "baseline (50/200 MA, 252/21 mom, 2% band)"}
    baseline_row.update({k: best_a[k] for k in
                          ("is_sharpe", "is_cagr", "is_trades", "is_win_rate",
                           "oos_sharpe", "oos_cagr", "oos_trades", "oos_win_rate")})
    rows_b = [baseline_row]

    variants = [
        ("faster trend (20/100 MA)", {"MA_FAST": 20, "MA_SLOW": 100}),
        ("6-1 month momentum (126/21)", {"MOM_LOOKBACK": 126, "MOM_SKIP": 21}),
        ("tighter pullback band (1%)", {"PULLBACK_BAND_PCT": 0.01}),
        ("looser pullback band (3%)", {"PULLBACK_BAND_PCT": 0.03}),
    ]

    for label, overrides in variants:
        saved = {k: getattr(config, k) for k in overrides}
        for k, v in overrides.items():
            setattr(config, k, v)
        wide_b, ts_b, sr_b, d_b = backtest._build_wide_frames(uni)
        returns, trades, _ = backtest.simulate(wide_b, ts_b, sr_b, d_b, STOP, TARGET, include_short=False)
        row = {"label": label}
        row.update(_split_eval(returns, trades))
        rows_b.append(row)
        print(f"  {label}: IS Sharpe {row['is_sharpe']:.2f} CAGR {row['is_cagr']:.1%} | "
              f"OOS Sharpe {row['oos_sharpe']:.2f} CAGR {row['oos_cagr']:.1%}")
        for k, v in saved.items():
            setattr(config, k, v)

    df_b = pd.DataFrame(rows_b)
    print("\n=== Phase B summary (baseline = Phase A winner, unchanged structure) ===")
    print(df_b[["label", "is_trades", "is_win_rate", "is_cagr", "is_sharpe",
                "oos_trades", "oos_win_rate", "oos_cagr", "oos_sharpe"]].to_string(index=False))

    df_a.to_csv("tune2_phaseA.csv", index=False)
    df_b.to_csv("tune2_phaseB.csv", index=False)
    print("\nSaved: tune2_phaseA.csv, tune2_phaseB.csv (local only, not pushed)")


if __name__ == "__main__":
    main()
