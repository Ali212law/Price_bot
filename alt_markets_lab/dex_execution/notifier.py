import os
from decimal import Decimal

# ─── Core Settings ───
DRY_RUN = True  # فاز ۱: همیشه True. هرگز تغییر نده تا فاز ۳
CHAIN = "bsc"   # BNB Chain
DEX = "pancakeswap_v2"
PAIR = "BNB/USDT"

# ─── Safety Limits (بسیار محافظه‌کارانه) ───
MAX_TRADE_SIZE_USD = Decimal("10.00")     # سقف هر معامله: ۱۰ دلار
MAX_DAILY_TRADES = 5                      # سقف ۵ معامله در روز
MAX_DAILY_VOLUME_USD = Decimal("50.00")   # سقف حجم روزانه: ۵۰ دلار
TRANSACTION_TIMEOUT_SEC = 60              # انتظار حداکثر ۶۰ ثانیه
MIN_WALLET_BALANCE_USD = Decimal("20.00") # حداقل موجودی

# ─── Risk Management ───
DEFAULT_SL_PCT = 2.0   # حد ضرر: ۲٪
DEFAULT_TP_PCT = 4.0   # حد سود: ۴٪
MAX_POSITIONS = 2      # حداکثر ۲ پوزیشن باز همزمان

# ─── Notifications (Bale only for now) ───
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID", "")

# ─── HALT Mechanism ───
HALT_FILE = "HALT_FILE"
HALT_TRIGGERS = [
    "transaction_failed",
    "transaction_timeout",
    "daily_trade_limit_exceeded",
    "daily_volume_exceeded",
    "wallet_balance_too_low",
    "rpc_error",
]

# ─── GitHub Integration ───
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "alt_markets_lab/dex_execution/dex_state.json"
LOG_FILE = "alt_markets_lab/dex_execution/transfer_log.json"
