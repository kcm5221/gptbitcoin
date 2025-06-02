# trading_bot/config.py

import os
from pathlib import Path

PROJECT_ROOT  = Path(__file__).resolve().parent
DB_FILE       = PROJECT_ROOT / "data" / "trading.db"
CACHE_FILE    = PROJECT_ROOT / "ohlcv_cache.json"
LOG_DIR       = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

PATTERN_HISTORY_FILE = PROJECT_ROOT / "pattern_history.json"

DOTENV_PATH    = PROJECT_ROOT / ".env"

TICKER        = os.getenv("TICKER", "KRW-BTC")
INTERVAL      = os.getenv("INTERVAL", "minute15")  # 15분봉 전용
CACHE_TTL     = int(os.getenv("CACHE_TTL", "3600"))  # 초 단위
MIN_ORDER_KRW = int(os.getenv("MIN_ORDER_KRW", "5000"))

ACCESS_KEY    = os.getenv("UPBIT_ACCESS_KEY", "").strip()
SECRET_KEY    = os.getenv("UPBIT_SECRET_KEY", "").strip()
LIVE_MODE     = (os.getenv("LIVE_MODE", "false").lower() == "true"
                 and ACCESS_KEY and SECRET_KEY)

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

PLAY_RATIO    = float(os.getenv("PLAY_RATIO", "0.05"))
RESERVE_RATIO = float(os.getenv("RESERVE_RATIO", "0.10"))

FG_CACHE_TTL = int(os.getenv("FG_CACHE_TTL", "82800"))

SMA_WIN   = int(os.getenv("SMA_WIN", "30"))
ATR_WIN   = int(os.getenv("ATR_WIN", "14"))

BUY_PCT   = float(os.getenv("BUY_PCT", "1.0"))
SELL_PCT  = float(os.getenv("SELL_PCT", "0.50"))
FG_BUY_TH = int(os.getenv("FG_BUY_TH", "40"))
FG_SELL_TH= int(os.getenv("FG_SELL_TH", "70"))
BASE_RISK = float(os.getenv("BASE_RISK", "0.02"))

VOLUME_THRESHOLD   = float(os.getenv("VOLUME_THRESHOLD", "2.0"))

# 1시간봉 지표 계산에 사용할 EMA/RSI 윈도우
EMA_FAST_WINDOW = int(os.getenv("EMA_FAST_WINDOW", "12"))
EMA_SLOW_WINDOW = int(os.getenv("EMA_SLOW_WINDOW", "26"))
RSI_WINDOW      = int(os.getenv("RSI_WINDOW", "14"))
