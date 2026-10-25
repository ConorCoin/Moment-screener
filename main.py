"""Daily entry point: refresh universe, update prices, run the screen, write the report.

Run this once per day after market close (see README for scheduling it on Windows Task Scheduler).
"""

import sys
import time

import config
import data
import report
import screener
import universe


def run_daily():
    t0 = time.time()
    print("[1/4] Refreshing universe (S&P 500 + Nasdaq 100)...")
    uni = universe.build_universe()
    print(f"      {len(uni)} tickers in universe.")

    print("[2/4] Updating price history...")
    all_tickers = uni["ticker"].tolist() + list(config.SECTOR_ETFS.keys()) + [config.BENCHMARK]
    failed = data.update_prices(all_tickers)
    print(f"      Updated {len(all_tickers) - len(failed)} tickers, {len(failed)} failed.")
    if failed:
        print(f"      Failed tickers (will be skipped by the screen): {failed}")

    print("[3/4] Running screen...")
    results = screener.run_screen()
    print(f"      {len(results['long_triggers'])} long triggers, {len(results['short_triggers'])} short triggers today.")

    print("[4/4] Writing report...")
    path = report.save_report(results)
    print(f"      Report saved to: {path}")

    print(f"\nDone in {time.time() - t0:.1f}s.")
    return results


if __name__ == "__main__":
    try:
        run_daily()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
