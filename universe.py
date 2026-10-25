"""Builds and caches the trading universe: S&P 500 + Nasdaq 100, with a sector-ETF mapping."""

import io
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import config

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NDX_URL = "https://www.slickcharts.com/nasdaq100"

HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: local use)"}

# Maps the sector labels Wikipedia/GICS uses to the SPDR sector ETF that tracks them.
GICS_TO_ETF = {
    "Information Technology": "XLK",
    "Technology": "XLK",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Health Care": "XLV",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Telecommunication Services": "XLC",
}


def _fetch_sp500() -> pd.DataFrame:
    html = requests.get(SP500_URL, headers=HEADERS, timeout=30).text
    table = pd.read_html(io.StringIO(html))[0]
    df = table[["Symbol", "GICS Sector"]].rename(columns={"Symbol": "ticker", "GICS Sector": "sector"})
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B for yfinance
    return df


def _fetch_nasdaq100() -> pd.DataFrame:
    html = requests.get(NDX_URL, headers=HEADERS, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    # slickcharts.com/nasdaq100 publishes one real table with a "Symbol" column.
    for t in tables:
        if "Symbol" in t.columns and len(t) >= 90:
            df = t[["Symbol"]].rename(columns={"Symbol": "ticker"})
            df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)
            df["sector"] = None  # filled in by merge against S&P list, or left unknown
            return df
    raise RuntimeError("Could not find Nasdaq-100 constituents table")


def _fill_unknown_sectors(df: pd.DataFrame) -> pd.DataFrame:
    """Best-effort yfinance lookup for tickers the Wikipedia merge couldn't sector-tag
    (mostly Nasdaq-100 names, e.g. foreign ADRs, not also in the S&P 500)."""
    import yfinance as yf

    unknown = df[df["sector_etf"] == "Unknown"]["ticker"].tolist()
    for ticker in unknown:
        try:
            info = yf.Ticker(ticker).get_info()
            yf_sector = info.get("sector")
            etf = GICS_TO_ETF.get(yf_sector, "Unknown")
            df.loc[df["ticker"] == ticker, "sector"] = yf_sector or "Unknown"
            df.loc[df["ticker"] == ticker, "sector_etf"] = etf
        except Exception:
            continue  # leave as Unknown; screener will just skip it
    return df


def build_universe(force_refresh: bool = False) -> pd.DataFrame:
    """Returns a DataFrame[ticker, sector, sector_etf], cached locally for UNIVERSE_REFRESH_DAYS."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = config.UNIVERSE_CACHE_FILE

    if not force_refresh and cache_file.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age < timedelta(days=config.UNIVERSE_REFRESH_DAYS):
            return pd.read_csv(cache_file)

    sp500 = _fetch_sp500()
    time.sleep(1)
    ndx = _fetch_nasdaq100()

    merged = pd.concat([sp500, ndx], ignore_index=True)
    merged = merged.drop_duplicates(subset="ticker", keep="first")
    # Nasdaq-100 names not already in the S&P list have sector=None; best-effort fill later via yfinance if needed.
    merged["sector"] = merged["sector"].fillna("Unknown")
    merged["sector_etf"] = merged["sector"].map(GICS_TO_ETF).fillna("Unknown")
    merged = _fill_unknown_sectors(merged)

    merged.to_csv(cache_file, index=False)
    return merged


if __name__ == "__main__":
    uni = build_universe(force_refresh=True)
    print(f"Universe size: {len(uni)} tickers")
    print(uni["sector_etf"].value_counts())
    print(uni[uni["sector_etf"] == "Unknown"].head(20))
