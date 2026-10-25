# Momentum Screener

Daily end-of-day screener: sector rotation + relative-strength momentum, trend-confirmed
(not breakout) entries, both long and short. Generates a daily watchlist — it does **not**
place trades for you.

## How it works

1. **Universe**: S&P 500 + Nasdaq 100 (deduped), sector-tagged via GICS/SPDR sector ETF mapping.
2. **Sector rotation**: ranks the 11 SPDR sector ETFs by relative strength vs. SPY (blended
   3-month / 6-month). Top 4 = leading sectors (long universe), bottom 4 = lagging (short universe).
3. **Trend filter**: within leading sectors, only stocks in a confirmed uptrend qualify
   (price > rising 50dma > rising 200dma); mirrored for lagging sectors/downtrends.
4. **Momentum ranking**: 12-1 month momentum (classic cross-sectional momentum factor),
   top decile of qualifying longs, bottom decile of qualifying shorts.
5. **Entry trigger**: a candidate "triggers" when it pulls back near its 50dma and closes
   back through it in the trend direction — not a breakout trigger.
6. **Stop/target**: fixed % off entry price (defaults: 7% stop / 15% target — see `config.py`).

Signals are based on the day's closing price, so you act on them in the **next** session.

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

## What this is and isn't

- This is a **signal generator**, not an autotrader. You review `reports/<date>.md` and
  decide whether to act.
- The short side is designed to be expressed via **puts or put spreads**, not naked short
  stock — naked shorts carry theoretically unlimited risk; a long put caps your risk at
  the premium paid.
- Stop/target % are a simple starting default, not backtested or optimized. Before trading
  this for real, backtest it (walk-forward, with realistic costs) and paper-trade it for a
  while — this build intentionally skipped backtesting per your request to get the live
  pipeline working first.
- Sector mapping, universe lists, and data quality all rely on free sources (Wikipedia,
  slickcharts, yfinance) — spot-check it periodically rather than assuming it's always
  perfectly current.

## Tunable parameters

All in `config.py`: moving average periods, momentum lookback/skip, pullback band,
stop/target %, number of leading/lagging sectors, top-decile cutoff.
