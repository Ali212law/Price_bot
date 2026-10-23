import os
from decimal import Decimal

DRY_RUN = True
CHAIN = "bsc"
DEX = "pancakeswap_v2"
PAIR = "BNB/USDT"

MAX_TRADE_SIZE_USD = Decimal("10.00")
MAX_DAILY_TRADES = 5
MAX_DAILY_VOLUME_USD = Decimal("50.00")
TRANSACTION_TIMEOUT_SEC = 60
MIN_WALLET_BALANCE_USD = Decimal("20.00")

DEFAULT_SL_PCT = 2.0
DEFAULT_TP_PCT = 4.0
MAX_POSITIONS = 2

BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID", "")

HALT_FILE = "HALT_FILE"
HALT_TRIGGERS = [
    "transaction_failed",
    "transaction_timeout",
    "daily_trade_limit_exceeded",
    "daily_volume_exceeded",
    "wallet_balance_too_low",
    "rpc_error",
]

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "alt_markets_lab/dex_execution/dex_state.json"
LOG_FILE = "alt_markets_lab/dex_execution/transfer_log.json"
