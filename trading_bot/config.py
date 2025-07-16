# trading_bot/config.py

from dotenv import load_dotenv
from pathlib import Path
import logging

# 환경 변수는 저장소 루트의 .env 파일에서 로드합니다
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger(__name__)

def log_env_info() -> None:
    """Log .env path and OPENAI_API_KEY value for debugging."""
    logger.info(
        f".env 경로: {ENV_PATH}, OPENAI_API_KEY={os.getenv('OPENAI_API_KEY')}"
    )

import os

# ──────────────────────────────────────────────────────────────────────
# 프로젝트 기본 경로 및 환경 변수 로드
# ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_FILE = DATA_DIR / "trading.db"
CACHE_FILE = DATA_DIR / "ohlcv_cache.json"
# 로그 디렉터리
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 패턴 히스토리 저장 파일 (ai_helpers.py에서 사용)
PATTERN_HISTORY_FILE = DATA_DIR / "pattern_history.json"
# FNG 지수 캐시 파일 (utils.py에서 사용)
FNG_CACHE_FILE = DATA_DIR / "fng_cache.json"
# AI 반성문 캐시 파일 (ai_helpers.py에서 사용)
REFLECTION_CACHE_FILE = DATA_DIR / "reflection_cache.json"
# ──────────────────────────────────────────────────────────────────────

# 1) 기본 환경 변수
TICKER = os.getenv("TICKER", "KRW-BTC")
INTERVAL = os.getenv("INTERVAL", "minute15")
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
FG_CACHE_TTL = int(os.getenv("FG_CACHE_TTL", "82800"))
MIN_ORDER_KRW = int(os.getenv("MIN_ORDER_KRW", "5000"))

ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "").strip()
SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "").strip()
# Enable live trading only when the flag is "true" and both API keys are provided
LIVE_MODE = (
    os.getenv("LIVE_MODE", "false").lower() == "true"
    and bool(ACCESS_KEY)
    and bool(SECRET_KEY)
)

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

PLAY_RATIO = float(os.getenv("PLAY_RATIO", "0.05"))
RESERVE_RATIO = float(os.getenv("RESERVE_RATIO", "0.10"))
BASE_RISK = float(os.getenv("BASE_RISK", "0.02"))

# 2) 가상 계좌 기본값
INITIAL_KRW = float(os.getenv("INITIAL_KRW", "30000.0"))

# 3) “Fear & Greed” 지수 임계치
FG_BUY_TH = int(os.getenv("FG_BUY_TH", "40"))
FG_SELL_TH = int(os.getenv("FG_SELL_TH", "70"))

# 4) 전략 관련 파라미터

# 4.1) 이동평균/지표 윈도우
SMA_WINDOW = int(os.getenv("SMA_WINDOW", "30"))
EMA_FAST_WINDOW = int(os.getenv("EMA_FAST_WINDOW", "12"))
EMA_SLOW_WINDOW = int(os.getenv("EMA_SLOW_WINDOW", "26"))
RSI_WINDOW = int(os.getenv("RSI_WINDOW", "14"))
ATR_WINDOW = int(os.getenv("ATR_WINDOW", "16"))

# 4.2) 볼륨 스파이크 임계치
_raw = os.getenv("VOLUME_SPIKE_THRESHOLD", "0.25")
VOLUME_SPIKE_THRESHOLD = float(_raw.split("#", 1)[0].strip())

_raw = os.getenv("AI_NOISE_VOL_THRESHOLD", "0.10")
AI_NOISE_VOL_THRESHOLD = float(_raw.split("#", 1)[0].strip())

# 4.3) rule-based 노이즈 필터 임계치
_raw = os.getenv("NOISE_VOL_THRESHOLD", "0.02")
NOISE_VOL_THRESHOLD = float(_raw.split("#", 1)[0].strip())

_raw = os.getenv("PRICE_RANGE_THRESHOLD", "0.10")
PRICE_RANGE_THRESHOLD = float(_raw.split("#", 1)[0].strip())

# 4.4) 손절/익절 비율
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.06"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.05"))

# 4.5) 매매 수수료 (Upbit 시장가)
TRADING_FEE = float(os.getenv("TRADING_FEE", "0.0005"))

# 4.6) EMA 교차 밴드 임계치 (whipsaw 완화)
EMA_CROSS_BAND = float(os.getenv("EMA_CROSS_BAND", "0.5"))

# 5) 캔들 패턴 관련 파라미터

DOJI_TOLERANCE = float(os.getenv("DOJI_TOLERANCE", "0.001"))
DOUBLE_BOTTOM_REBOUND_PCT = float(os.getenv("DOUBLE_BOTTOM_REBOUND_PCT", "0.01"))
DOUBLE_TOP_DROP_PCT = float(os.getenv("DOUBLE_TOP_DROP_PCT", "0.01"))
DOUBLE_PATTERN_LOOKBACK = int(os.getenv("DOUBLE_PATTERN_LOOKBACK", "3"))

# 6) 1시간봉 SMA50 예외용 파라미터

_raw = os.getenv("RSI_OVERRIDE", "40.0")
RSI_OVERRIDE = float(_raw.split("#", 1)[0].strip())

_raw = os.getenv("MACD_1H_THRESHOLD", "2500.0")
MACD_1H_THRESHOLD = float(_raw.split("#", 1)[0].strip())

_raw = os.getenv("FG_EXTREME_FEAR", "50.0")
FG_EXTREME_FEAR = float(_raw.split("#", 1)[0].strip())

# 7) AI 반성문 관련 설정
REFLECTION_INTERVAL_HOURS = float(os.getenv("REFLECTION_INTERVAL_HOURS", "11"))
REFLECTION_INTERVAL_SEC = int(REFLECTION_INTERVAL_HOURS * 3600)
# AI 리플렉션을 GPT에게 한 번 더 개선 요청할지 여부 (기본 true)
REFLECTION_RECURSIVE = os.getenv("REFLECTION_RECURSIVE", "true").lower() == "true"
# KEY=VALUE 줄이 없을 때 추가 요청 시도 횟수 (기본 2)
REFLECTION_KV_RETRY = int(os.getenv("REFLECTION_KV_RETRY", "2"))

# 8) 데이터베이스 로그 보존 최대 행 수
LOG_RETENTION_ROWS = int(os.getenv("LOG_RETENTION_ROWS", "5000"))

# 오래된 로그 정리 후 VACUUM을 실행할지 여부 (기본 true)
ENABLE_DB_VACUUM = os.getenv("ENABLE_DB_VACUUM", "true").lower() == "true"
