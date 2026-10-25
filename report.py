"""Formats screen results into a daily markdown watchlist report."""

from datetime import date

import pandas as pd

import config


def _fmt_table(df: pd.DataFrame, cols: list[str]) -> str:
    if df.empty:
        return "_none_\n"
    show = df[cols].copy()
    if "momentum_12_1" in show.columns:
        show["momentum_12_1"] = show["momentum_12_1"].map(lambda x: f"{x:.1%}")
    if "rs_vs_spy" in show.columns:
        show["rs_vs_spy"] = show["rs_vs_spy"].map(lambda x: f"{x:.2%}")
    return show.to_markdown(index=False) + "\n"


def build_report(results: dict) -> str:
    today = date.today().isoformat()
    lines = [f"# Momentum Screener — {today}\n"]

    lines.append("## Sector leadership (ETF relative strength vs SPY)\n")
    lines.append(_fmt_table(results["sectors"], ["etf", "sector", "rs_vs_spy"]))

    lines.append("\n## LONG triggers today (buy)\n")
    lines.append(_fmt_table(results["long_triggers"], ["ticker", "sector_etf", "price", "momentum_12_1", "stop", "target"]))

    lines.append("\n## SHORT triggers today (via puts/put spreads)\n")
    lines.append(_fmt_table(results["short_triggers"], ["ticker", "sector_etf", "price", "momentum_12_1", "stop", "target"]))

    lines.append(f"\n## Long watchlist — in confirmed uptrend, top {config.TOP_DECILE:.0%} momentum, not yet triggered\n")
    watch_long = results["long_candidates"]
    watch_long = watch_long[~watch_long["triggered_today"]] if not watch_long.empty else watch_long
    lines.append(_fmt_table(watch_long, ["ticker", "sector_etf", "price", "momentum_12_1"]))

    lines.append(f"\n## Short watchlist — in confirmed downtrend, bottom {config.TOP_DECILE:.0%} momentum, not yet triggered\n")
    watch_short = results["short_candidates"]
    watch_short = watch_short[~watch_short["triggered_today"]] if not watch_short.empty else watch_short
    lines.append(_fmt_table(watch_short, ["ticker", "sector_etf", "price", "momentum_12_1"]))

    lines.append(f"\n---\nStop/target defaults: {config.STOP_LOSS_PCT:.0%} stop / {config.PROFIT_TARGET_PCT:.0%} target. "
                 f"Signals are based on today's close — act in the next session.\n")

    return "\n".join(lines)


def save_report(results: dict) -> str:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path = config.REPORTS_DIR / f"{today}.md"
    content = build_report(results)
    path.write_text(content, encoding="utf-8")
    return str(path)
