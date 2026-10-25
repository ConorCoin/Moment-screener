# Momentum Screener

Daily end-of-day screener: sector rotation + relative-strength momentum, trend-confirmed
(not breakout) entries. Generates a daily watchlist — it does **not** place trades for you.

## How it works

1. **Universe**: S&P 500 + Nasdaq 100 (deduped), sector-tagged via GICS/SPDR sector ETF mapping.
2. **Sector rotation**: ranks the 11 SPDR sector ETFs by relative strength vs. SPY (blended
   3-month / 6-month). Top 5 = leading sectors (long universe).
3. **Trend filter**: within leading sectors, only stocks in a confirmed uptrend qualify
   (price > rising 50dma > rising 200dma).
4. **Momentum ranking**: 6-1 month momentum, top 20% of qualifying longs.
5. **Entry trigger**: a candidate "triggers" when it pulls back near its 50dma, closes back
   above it, **and the day's volume exceeds its own 20-day average** (real buying interest,
   not just a price wiggle) — not a breakout trigger.
6. **Stop/target**: fixed % off entry price (7% stop / 10% target — see `config.py`).

Signals are based on the day's closing price, so you act on them in the **next** session.

## Backtested parameters (see "Backtest results" below)

Long-only. The exact parameters above (5 leading sectors, 20% top-decile cutoff, 6-1 month
momentum, 7% stop / 10% target) are the result of a walk-forward backtest over 2017-2026,
not the original arbitrary defaults. Shorting is disabled (`config.INCLUDE_SHORT = False`)
because backtesting showed the short side was a net loser over that period — set it back to
`True` if you want to re-enable it (e.g. the lagging-sector logic is still there, just unused).

## Running it

```
pip install -r requirements.txt
python main.py
```

This refreshes the universe list (cached for 7 days), updates local price history
(`data/prices/*.parquet`), runs the screen, and writes `reports/YYYY-MM-DD.md`.

Run the pieces individually for debugging:
- `python universe.py` — rebuild and print the universe
- `python data.py` — just update price data
- `python sector.py` — just print sector rankings
- `python screener.py` — run the screen and print results to console (no report file)

## Scheduling it daily (Windows Task Scheduler)

Run once per day after market close (data providers typically have final daily bars
available by ~6pm ET):

1. Open Task Scheduler → Create Basic Task.
2. Trigger: Daily, ~6:30pm.
3. Action: Start a program.
   - Program: path to your `python.exe`
   - Arguments: `main.py`
   - Start in: this project's folder (so relative paths resolve)
4. Skip weekends if you want (Task Scheduler's "Daily" trigger has no built-in weekday
   filter in Basic mode — use the "Weekly" trigger type instead and check Mon-Fri only).

Not set up yet in this build — ask if you want this wired up automatically.

## Recommended: qualitative review before acting on a trigger

This screener is 100% price/volume-based — it has no idea what a company actually does,
whether its earnings are improving or deteriorating, or what's happening in markets that day.
A name can trigger on pure price action while the underlying fundamentals are quietly rotting
(e.g. a short squeeze or hype-driven move with no earnings support).

Before acting on any `LONG triggers` / `SHORT triggers` line in a report, it's worth handing
that day's `reports/<date>.md` to an LLM agent (Claude, or your local model) with a prompt like:

> "Here's today's momentum screener output. For each triggered ticker, pull current market
> conditions, recent news/catalysts, and a quick fundamental sanity check (earnings trend,
> debt, any red flags). Flag anything where the technical signal looks disconnected from the
> fundamentals or the broader market backdrop."

This isn't built into the pipeline (deliberately — the screening logic itself should stay
deterministic and backtestable, not dependent on an LLM's non-reproducible judgment). Treat it
as a manual second opinion step between "the report triggered something" and "I place the trade."

## Backtest results (walk-forward, 2017-2026, see `backtest.py` / `tune.py` / `tune2.py` / `tune3.py`)

These are local analysis scripts (not part of the daily pipeline — `main.py` doesn't call
them). Their CSV/log outputs are gitignored since they're regenerable data, not code, but the
scripts themselves are here so the parameter choices below are reproducible, not just claimed:

- The original long+short, untuned defaults (7% stop/15% target, 12-1 month momentum, 4
  leading/4 lagging sectors) **badly underperformed buy-and-hold SPY**: 1.6% CAGR / 0.23 Sharpe
  vs. SPY's 14.4% CAGR / 0.81 Sharpe over the same window. The short side alone was a net
  loser (-1.85% avg return/trade).
- After tuning (long-only, wider stop kept at 7%, target lowered to 10%, wider 20% candidate
  pool, 5 leading sectors, 6-1 month momentum — i.e. the current `config.py` defaults):
  **in-sample (2017-2022) it slightly beat SPY** (10.6% CAGR / 0.91 Sharpe vs. SPY's 10.3% /
  0.58). **Out-of-sample (2023-2026) it still trailed** (7.1% CAGR / 0.64 Sharpe vs. SPY's
  21.3% / 1.38) — though that period was an exceptionally strong bull run for SPY specifically,
  not a typical stretch.
- **Tighter stops were tested and were worse**, not better — 4-5% stops underperformed the
  7% stop at every target level tried. Counterintuitive, but consistent across the whole grid.
- Caveats that still apply: **zero transaction costs/slippage modeled** on ~1,500+ trades in
  the tuned backtest — real costs would erode the edge further. The short-side backtest
  approximated puts as straight short-stock P&L, not real options pricing. Parameter selection
  used the out-of-sample period somewhat to break ties, so that holdout isn't perfectly blind —
  a truly rigorous check would validate against a third, never-touched period.

### Round 3: trying to reduce how often trades hit the stop (see `tune3.py`)

Tested five additional levers as a full factorial (32 combinations): ATR-based stop/target
sizing, 2-day entry confirmation, volume confirmation, a minimum trend-slope threshold, and a
trailing stop. Results were mostly disappointing or neutral:

- **ATR-based stops hurt clearly** (OOS Sharpe dropped from 0.54 to 0.13) — the 2x/3x ATR
  multiples used were a guess, not tuned, so this isn't a final verdict on ATR stops in
  general, just on this untested version of them.
- **Trailing stop increased the loss rate rather than reducing it** — it ratchets the stop off
  the running high/low since entry with no minimum profit cushion first, so a stock that
  wiggles up slightly then pulls back gets stopped near breakeven-or-worse instead of riding
  out normal noise. A design flaw in this implementation, not a verdict on trailing stops.
- **2-day confirmation and the slope threshold were both roughly a wash** — inconsistent
  between in-sample and out-of-sample, not worth the added complexity.
- **Volume confirmation, tested alone, was the standout** — out-of-sample Sharpe 0.85 vs. the
  0.65 baseline, with a slightly lower loss rate too. It's now `config.REQUIRE_VOLUME_CONFIRM
  = True` in the live screener. The other four were left off.

## What this is and isn't

- This is a **signal generator**, not an autotrader. You review `reports/<date>.md` and
  decide whether to act.
- If you re-enable shorting, express it via **puts or put spreads**, not naked short stock —
  naked shorts carry theoretically unlimited risk; a long put caps your risk at the premium paid.
- Even the tuned version is not a proven market-beater — see "Backtest results" above. It's
  better-tested than an arbitrary guess, not a validated edge you should size heavily.
- Sector mapping, universe lists, and data quality all rely on free sources (Wikipedia,
  slickcharts, yfinance) — spot-check it periodically rather than assuming it's always
  perfectly current.

## Tunable parameters

All in `config.py`: moving average periods, momentum lookback/skip, pullback band,
stop/target %, number of leading/lagging sectors, top-decile cutoff, `INCLUDE_SHORT` toggle.
