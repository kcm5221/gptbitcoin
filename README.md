# gptbitcoin Trading Bot

자동화된 비트코인 매매 봇입니다. Upbit 현물 마켓을 대상으로 15분봉 및 1시간봉 OHLCV 데이터를 기반으로 다양한 지표와 AI 보조 기능을 활용하며, 수수료·로그 로테이션·AI 리플렉션 등을 포함합니다.

## 📂 프로젝트 구조

gptbitcoin/
├── .env # 환경 변수 파일
├── .env.sample # 환경 변수 예시
├── .gitignore
├── deploy_and_run.sh # 배포 · 실행 스크립트 (cron용)
├── requirements.txt # 의존성 리스트
└── trading_bot/ # 주요 파이썬 모듈
├── init.py
├── account_sync.py # 실계좌 잔고 동기화 헬퍼
├── ai_helpers.py # GPT-4o 관련 헬퍼 (패턴 의사결정, 리플렉션 등)
├── candle_patterns.py # 룰 기반 캔들패턴 함수
├── candles.py # 개별 캔들 패턴 검사 (Hammer, Doji 등)
├── config.py # 설정 및 환경 변수 로드
├── context.py # SignalContext 데이터 클래스
├── data_fetcher.py # OHLCV 데이터 로드(15m/1h) 헬퍼
├── data_io.py # JSON/파일 입출력 헬퍼
├── db_helpers.py # SQLite DB 초기화·로그 기록 헬퍼
├── executor.py # 매매(주문) 실행 및 Discord 알림 로직
├── filters.py # 노이즈 필터링 로직 (룰+AI)
├── indicators.py # 15분봉 지표 계산 (SMA/ATR/MACD 등)
├── indicators_1h.py # 1시간봉 지표 계산 (SMA50/EMA/RSI/ATR 등)
├── main.py # 모듈화된 진입점 (python -m trading_bot.main)
├── noise_filters.py # AI 기반 노이즈 감지 헬퍼
├── patterns.py # 룰·AI 복합 패턴 검사 및 매매 의사결정
├── strategies.py # 보조 전략 A/B (볼륨+SMA, EMA 크로스 등)
├── utils.py # 공통 유틸리티 (캐시 로드, 계좌 로드, FNG, etc.)
├── data/ # 데이터/캐시 폴더
│ ├── ohlcv_cache.json # 15분봉 OHLCV 캐시 파일
│ └── trading.db # SQLite 거래 로그 (indicator_log, trade_log, account)
└── logs/ # 자동매매 시 생성되는 로그 파일들


---

## 🚀 설치 및 실행

### 1. 저장소 클론

```bash
git clone git@github.com:<USERNAME>/gptbitcoin.git
cd gptbitcoin

2. 가상환경 생성 및 의존성 설치

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

3. 환경 변수 설정 (.env 파일 생성)

LIVE_MODE=true
UPBIT_ACCESS_KEY=여기에_업비트_액세스키
UPBIT_SECRET_KEY=여기에_업비트_시크릿키
OPENAI_API_KEY=여기에_OpenAI_API_키
DISCORD_WEBHOOK_URL=여기에_디스코드_웹훅_URL
TICKER=KRW-BTC
INTERVAL=minute15

# (선택) 전략 파라미터
PLAY_RATIO=0.05
RESERVE_RATIO=0.10
FG_BUY_TH=40
FG_SELL_TH=70
SMA_WIN=25
ATR_WIN=16
VOLUME_THRESHOLD=1.5
EMA_FAST_WINDOW=12
EMA_SLOW_WINDOW=26
RSI_WINDOW=14
MIN_ORDER_KRW=5000
CACHE_TTL=3600
FG_CACHE_TTL=82800
BASE_RISK=0.02

    주의: .env 파일에 민감한 API 키를 절대 공개 저장소에 커밋하지 마세요.

4. 데이터베이스 & 캐시 초기화

    첫 실행 시 trading_bot/config.py 에서 지정한 경로(기본 trading_bot/data/trading.db)에 DB 파일이 자동 생성됩니다.

    마찬가지로 ohlcv_cache.json도 같은 폴더에 저장됩니다.

5. 자동매매 스크립트 실행
5-1. 로컬에서 수동 실행

# 가상환경을 활성화한 상태에서
python3 -m trading_bot.main --mode intraday

    --mode intraday 옵션은 현재 인트라데이(15분봉+1시간봉) 모드로 실행합니다.

    첫 실행 후 DB (trading.db)와 캐시(ohlcv_cache.json)가 생성됩니다.

    성공적으로 실행되면 콘솔과 trading_bot/logs/에 로그가 찍히고, 실제 매매(실거래) 모드에서는 Discord 알림이 발송됩니다.

5-2. 배포용 스크립트 사용

리모트 서버(VM)에서는 deploy_and_run.sh를 호출하여 한 번에 업데이트 → 설치 → 실행을 할 수 있습니다.

./deploy_and_run.sh --mode intraday

deploy_and_run.sh 내부:

#!/usr/bin/env bash
set -euo pipefail

# 1) 리포지토리 최신화
cd /home/ubuntu/gptbitcoin

# 2) 가상환경 활성화
source /home/ubuntu/gptbitcoin/venv/bin/activate

# 3) 의존성 설치 (필요 시)
pip install --upgrade pip
pip install -r requirements.txt

# 4) 자동매매 스크립트 실행 (인트라데이 모드) & 로그를 cron.log에 덧붙이기
python3 -m trading_bot.main --mode intraday \
    >> /home/ubuntu/gptbitcoin/logs/cron.log 2>&1

⏰ 스케줄링 예시 (cron)

예를 들어, 한국 시간 기준 매일 특정 구간(인트라데이 영업 시간)에 15분마다 실행하도록 설정하려면:

# ──────────────────────────────────────────────────
# 한국 시간 02:00~05:59 구간 (UTC 전날 17:00~20:59) 매 15분마다
*/15 17-20 * * * /home/ubuntu/gptbitcoin/deploy_and_run.sh --mode intraday

# 한국 시간 14:00~17:59 구간 (UTC 당일 05:00~08:59) 매 15분마다
*/15 5-8   * * * /home/ubuntu/gptbitcoin/deploy_and_run.sh --mode intraday
# ──────────────────────────────────────────────────

    예시에서는 deploy_and_run.sh --mode intraday를 15분 간격으로 실행하고,
    표준 출력/오류는 logs/cron.log로 넘어갑니다.

⚙️ 주요 기능 설명

    LIVE / VIRTUAL 모드 분리

        LIVE_MODE=true일 때 실제 Upbit 계좌로 시장가 주문을 냅니다.

        LIVE_MODE=false일 때 가상 계좌(데이터베이스 내 샌드박스)만 시뮬레이션합니다.

    잔고 동기화

        trading_bot/account_sync.py에서 Upbit API(Upbit.get_balances)를 호출해
        실계좌 KRW, BTC, 평균 매수가를 가져옵니다.

    OHLCV 캐시 & REST 백업

        trading_bot/data_fetcher.py에서 load_cached_ohlcv()를 먼저 시도하고,
        캐시가 없거나 TTL(CACHE_TTL초)이 지났으면 pyupbit.get_ohlcv() → REST API 백업을 순차적으로 호출합니다.

    지표 계산

        15분봉 지표 (trading_bot/indicators.py):

            SMA(SMA_WIN), ATR(ATR_WIN), 20봉 평균 거래량(vol20), MACD diff

        1시간봉 지표 (trading_bot/indicators_1h.py):

            SMA50, EMA fast(EMA_FAST_WINDOW), EMA slow(EMA_SLOW_WINDOW), RSI(RSI_WINDOW), ATR(ATR_WIN)

    “Fear & Greed” 지수 (FNG)

        trading_bot/utils.py 내 get_fear_and_greed()가
        alternative.me API를 호출해 “공포·탐욕 지수”를 가져오고,
        하루(또는 FG_CACHE_TTL초) 동안 캐시로 재사용합니다.

    룰 기반 패턴 + AI 보조 패턴

        trading_bot/filters.py

            최근 5봉 노이즈(이상치) 검사: 볼륨 극단 감소 시 AI(ask_noise_filter)에게 물어봅니다.

        trading_bot/patterns.py

            룰 기반 단일/다중 캔들패턴:

                이중바닥, 이중천장, 망치형·역망치형·도지+볼륨 스파이크 → 매수/매도

                Stop-loss(94% 이하), Take-profit(5% 이상), Trend-sell(FNG+MACD)

            AI 복합 패턴:

                최근 100봉 데이터를 GPT-4o에 보내 “복합 차트 패턴”을 태깅하고,

                이미 룰에 정의된 패턴(KNOWN_PATTERNS)이 아니면, AI에게 “buy/sell/hold” 의사결정을 요청합니다.

                새로운 패턴은 trading_bot/data/pattern_history.json에 기록해둡니다.

    보조 전략 A / B

        A. 볼륨 스파이크 + price > SMA30 → 매수 / price < SMA30 → 매도

        B. EMA(12/26) 골든 크로스 → 매수 / 데드 크로스 → 매도

        두 보조 전략은 룰·AI 패턴에 아무 신호가 없을 때 차례로 동작합니다.

    실제 주문 실행 (시장가) + 동적 리스크 관리

        trading_bot/executor.py

            ATR 기반으로 “포지션 크기”를 1% 리스크 기준으로 동적 계산

            최소 주문액(MIN_ORDER_KRW) 미만이면 주문하지 않음

            실거래 모드(LIVE_MODE)에서는 Upbit 시장가 주문

            가상 모드에서는 DB 계좌에서 가상 계산만 수행

    로그 기록 & Discord 알림

        trading_bot/db_helpers.py

            SQLite 테이블: account(id=1), indicator_log, trade_log (자동 생성)

        trading_bot/executor.py → log_and_notify()

            매매 신호를 DB(trade_log)에 기록하고,

            실제 주문이 체결되었을 때만 Discord Webhook에 알림을 보냅니다.

            (원치 않으면 DISCORD_WEBHOOK_URL을 빈 문자열로 두시면 알림이 가지 않습니다.)

🛡️ 보안 주의 사항

    .env 파일에는 API 키를 절대 공개 저장소에 올리지 마십시오.
    GitHub 등에는 .env를 포함하지 않도록 이미 .gitignore에 지정되어 있습니다.

    requirements.txt에는 외부 라이브러리 목록만 기록하고,
    민감한 정보는 코드 또는 환경 변수로 관리합니다.

📜 라이선스

이 프로젝트의 저작권은 본인(© KCM)에게 있습니다.
