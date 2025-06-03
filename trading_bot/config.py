from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# 프로젝트 기본 경로 및 환경 변수 로드
# ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).resolve().parent
DATA_DIR      = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_FILE       = DATA_DIR / "trading.db"
CACHE_FILE    = DATA_DIR / "ohlcv_cache.json"
LOG_DIR       = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────
# 패턴 히스토리 저장 파일
# ──────────────────────────────────────────────────────────────────────
PATTERN_HISTORY_FILE = DATA_DIR / "pattern_history.json"
DOTENV_PATH = PROJECT_ROOT / ".env"

# ──────────────────────────────────────────────────────────────────────
# 1) 기본 환경 변수
# ──────────────────────────────────────────────────────────────────────
TICKER        = os.getenv("TICKER", "KRW-BTC")
INTERVAL      = os.getenv("INTERVAL", "minute15")
CACHE_TTL     = int(os.getenv("CACHE_TTL", "3600"))
FG_CACHE_TTL  = int(os.getenv("FG_CACHE_TTL", "82800"))
MIN_ORDER_KRW = int(os.getenv("MIN_ORDER_KRW", "5000"))

ACCESS_KEY    = os.getenv("UPBIT_ACCESS_KEY", "").strip()
SECRET_KEY    = os.getenv("UPBIT_SECRET_KEY", "").strip()
LIVE_MODE     = (
    os.getenv("LIVE_MODE", "false").lower() == "true"
    and ACCESS_KEY and SECRET_KEY
)

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

PLAY_RATIO    = float(os.getenv("PLAY_RATIO", "0.05"))
RESERVE_RATIO = float(os.getenv("RESERVE_RATIO", "0.10"))

# ──────────────────────────────────────────────────────────────────────
# 2) 가상 계좌 기본값
# ──────────────────────────────────────────────────────────────────────
INITIAL_KRW  = float(os.getenv("INITIAL_KRW", "30000.0"))

# ──────────────────────────────────────────────────────────────────────
# 3) “Fear & Greed” 지수 임계치
# ──────────────────────────────────────────────────────────────────────
FG_BUY_TH    = int(os.getenv("FG_BUY_TH", "40"))
FG_SELL_TH   = int(os.getenv("FG_SELL_TH", "70"))

# ──────────────────────────────────────────────────────────────────────
# 4) 전략 관련 파라미터
# ──────────────────────────────────────────────────────────────────────

# 4.1) 이동평균/지표 윈도우
SMA_WINDOW      = int(os.getenv("SMA_WINDOW", "30"))
EMA_FAST_WINDOW = int(os.getenv("EMA_FAST_WINDOW", "12"))
EMA_SLOW_WINDOW = int(os.getenv("EMA_SLOW_WINDOW", "26"))
RSI_WINDOW      = int(os.getenv("RSI_WINDOW", "14"))
ATR_WINDOW      = int(os.getenv("ATR_WINDOW", "16"))

# 4.2) 볼륨 스파이크 임계치
VOLUME_SPIKE_THRESHOLD      = float(os.getenv("VOLUME_SPIKE_THRESHOLD", "2.0"))
AI_NOISE_VOL_THRESHOLD      = float(os.getenv("AI_NOISE_VOL_THRESHOLD", "0.10"))

# 4.3) 손절/익절 비율
STOP_LOSS_PCT    = float(os.getenv("STOP_LOSS_PCT", "0.06"))
TAKE_PROFIT_PCT  = float(os.getenv("TAKE_PROFIT_PCT", "0.05"))

# 4.4) 매매 수수료 (Upbit 시장가)
TRADING_FEE      = float(os.getenv("TRADING_FEE", "0.0005"))

# 4.5) EMA 교차 밴드 임계치 (whipsaw 완화)
EMA_CROSS_BAND  = float(os.getenv("EMA_CROSS_BAND", "0.5"))

# ──────────────────────────────────────────────────────────────────────
# 5) 캔들 패턴 관련 파라미터
# ──────────────────────────────────────────────────────────────────────

# 도지 판정 허용 범위
DOJI_TOLERANCE              = float(os.getenv("DOJI_TOLERANCE", "0.001"))
# 이중바닥 반등 퍼센트 (예: 0.01 → 1% 반등)
DOUBLE_BOTTOM_REBOUND_PCT   = float(os.getenv("DOUBLE_BOTTOM_REBOUND_PCT", "0.01"))
# 이중천장 하락 퍼센트 (예: 0.01 → 1% 하락)
DOUBLE_TOP_DROP_PCT         = float(os.getenv("DOUBLE_TOP_DROP_PCT", "0.01"))
# 최근 N봉(예: 3봉) 중 연속 검사
DOUBLE_PATTERN_LOOKBACK     = int(os.getenv("DOUBLE_PATTERN_LOOKBACK", "3"))

# ──────────────────────────────────────────────────────────────────────
# 6) 노이즈 필터 관련 임계치
# ──────────────────────────────────────────────────────────────────────

# “이전 4봉 평균 거래량 대비 얼마 이하를 노이즈로 볼 것인가”
NOISE_VOL_THRESHOLD      = float(os.getenv("NOISE_VOL_THRESHOLD", "0.02"))
# “고가-저가 범위가 종가의 몇 배 이상이면 노이즈로 볼 것인가”
PRICE_RANGE_THRESHOLD    = float(os.getenv("PRICE_RANGE_THRESHOLD", "0.10"))

# ──────────────────────────────────────────────────────────────────────
# 7) 1시간봉 SMA50 예외용 파라미터
# ──────────────────────────────────────────────────────────────────────

# 1h RSI 예외 허용: 1시간봉 RSI ≤ 이 값이면 SMA50 아래여도 진입 허용
RSI_OVERRIDE       = float(os.getenv("RSI_OVERRIDE", "40.0"))
# 1h MACD diff 절대값 기준: |MACD diff| ≤ 이 값이면 모멘텀 약함으로 보고 진입 허용
MACD_1H_THRESHOLD  = float(os.getenv("MACD_1H_THRESHOLD", "2500.0"))
# 1h Fear-Greed 지수 예외 허용: 공포국면이면 진입 허용
FG_EXTREME_FEAR    = float(os.getenv("FG_EXTREME_FEAR", "50.0"))
