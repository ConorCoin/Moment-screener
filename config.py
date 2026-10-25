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
N_LEADING_SECTORS = 4
N_LAGGING_SECTORS = 4

# --- Momentum ranking (12-1 month, classic cross-sectional momentum) ---
MOM_LOOKBACK = 252  # ~12 months
MOM_SKIP = 21       # exclude most recent ~1 month
TOP_DECILE = 0.10   # top/bottom 10% of ranked candidates within qualifying sectors

# --- Entry trigger: pullback to the rising/falling 50dma, then close back through it ---
PULLBACK_BAND_PCT = 0.02  # price must come within 2% of the 50dma to count as "pulled back"

# --- Exit: fixed profit target / stop loss (% off entry price) ---
STOP_LOSS_PCT = 0.07
PROFIT_TARGET_PCT = 0.15

# --- Universe refresh ---
UNIVERSE_CACHE_FILE = CACHE_DIR / "universe.csv"
UNIVERSE_REFRESH_DAYS = 7
