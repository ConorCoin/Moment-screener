"""Tunable parameters for the momentum screener."""

from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data" / "prices"
CACHE_DIR = ROOT / "cache"
REPORTS_DIR = ROOT / "reports"

# --- History needed ---
LOOKBACK_DAYS = 420  # >14 months of trading days, covers 200dma + 12-1mo momentum

# --- Trend filter ---
MA_FAST = 50
MA_SLOW = 200
MA_SLOPE_LOOKBACK = 20  # days back to compare MA value against, to judge "rising"/"falling"

# --- Sector rotation ---
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financial Services",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLY": "Consumer Cyclical",
    "XLP": "Consumer Defensive",
    "XLI": "Industrials",
    "XLB": "Basic Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}
BENCHMARK = "SPY"
SECTOR_RS_WINDOWS = (63, 126)  # ~3mo, ~6mo trading days
N_LEADING_SECTORS = 5   # tuned: backtest.py / tune2.py, see README "Backtested parameters"
N_LAGGING_SECTORS = 4   # unused while INCLUDE_SHORT=False, kept for if shorting is re-enabled

# --- Direction: backtesting showed the short side was a net loser (see README) ---
INCLUDE_SHORT = False

# --- Momentum ranking (6-1 month; tuned down from the classic 12-1 month convention) ---
MOM_LOOKBACK = 126  # ~6 months — tuned: improved both in-sample and out-of-sample
MOM_SKIP = 21        # exclude most recent ~1 month
TOP_DECILE = 0.20    # top/bottom 20% of ranked candidates — tuned wider from 10%

# --- Entry trigger: pullback to the rising/falling 50dma, then close back through it ---
PULLBACK_BAND_PCT = 0.02  # price must come within 2% of the 50dma to count as "pulled back"

# --- Exit: fixed profit target / stop loss (% off entry price) ---
STOP_LOSS_PCT = 0.07       # unchanged — tested tighter stops (4%, 5%) and they were worse
PROFIT_TARGET_PCT = 0.10   # tuned down from 15%

# --- Universe refresh ---
UNIVERSE_CACHE_FILE = CACHE_DIR / "universe.csv"
UNIVERSE_REFRESH_DAYS = 7
