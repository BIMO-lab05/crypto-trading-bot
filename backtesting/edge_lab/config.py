"""Battery-wide pinned constants. Declared before any run; changing a value
after verdicts exist invalidates them (spec §4 anti-overfitting rule)."""

from decimal import Decimal

from shared.account import ACCOUNT_EQUITY_USD

UNIVERSE_TOP_N = 30
MIN_LISTING_AGE_DAYS = 730
DAILY_LOOKBACK_DAYS = 730
H4_LOOKBACK_DAYS = 365
H4_INTERVAL = "240"
DAILY_INTERVAL = "D"  # Bybit API interval; filenames use 1440m (killtest convention)

HURDLE_MULTIPLE = Decimal("2")
SLIPPAGE_BPS = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}
SLIPPAGE_FALLBACK_BPS = Decimal(
    "10"
)  # every non-major: 11 fee + 20 slip = 31 bps RT taker

DSR_THRESHOLD = 0.95
NUM_TRIALS_FLOOR = 16  # 8 battery variants + 8 historical families (CLAUDE.md §2)
MIN_POSITIVE_PATH_FRAC = 0.70
CPCV_N_GROUPS = 10
CPCV_K_TEST_GROUPS = 2
CPCV_EMBARGO_PCT = 0.01

NOTIONAL_PER_TRADE = Decimal(str(ACCOUNT_EQUITY_USD))
