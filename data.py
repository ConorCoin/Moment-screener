"""Downloads and locally caches daily OHLCV for the universe + sector ETFs + benchmark."""

from pathlib import Path

import pandas as pd
import yfinance as yf

import config


def _parquet_path(ticker: str) -> Path:
    return config.DATA_DIR / f"{ticker}.parquet"


def _download_batch(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Downloads a batch of tickers in one yfinance call; returns {ticker: df}."""
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    out = {}
    if len(tickers) == 1:
        t = tickers[0]
        df = raw.dropna(how="all")
        if not df.empty:
            out[t] = df
        return out
    for t in tickers:
        try:
            df = raw[t].dropna(how="all")
            if not df.empty:
                out[t] = df
        except (KeyError, IndexError):
            continue
    return out


def update_prices(tickers: list[str], batch_size: int = 50, period: str = "2y") -> list[str]:
    """Updates local parquet cache for each ticker. Returns list of tickers that failed."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        results = _download_batch(batch, period=period)
        for t in batch:
            if t in results:
                results[t].to_parquet(_parquet_path(t))
            else:
                failed.append(t)
    return failed


def load_prices(ticker: str) -> pd.DataFrame | None:
    path = _parquet_path(ticker)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def load_all(tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for t in tickers:
        df = load_prices(t)
        if df is not None and len(df) > config.MA_SLOW:
            out[t] = df
    return out


if __name__ == "__main__":
    import universe

    uni = universe.build_universe()
    sector_etfs = list(config.SECTOR_ETFS.keys()) + [config.BENCHMARK]
    all_tickers = uni["ticker"].tolist() + sector_etfs

    print(f"Downloading {len(all_tickers)} tickers...")
    failed = update_prices(all_tickers)
    print(f"Done. {len(all_tickers) - len(failed)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed:", failed[:30])
