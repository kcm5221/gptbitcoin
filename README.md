# gptbitcoin Trading Bot

자동화된 비트코인 매매 봇입니다. Upbit 현물 마켓을 대상으로 15분봉 및 1시간봉 OHLCV 데이터를 기반으로 다양한 지표와 AI 보조 기능을 활용하며, 수수료·로그 로테이션·AI 리플렉션 등을 포함합니다.

## 📂 프로젝트 구조
```
gptbitcoin/
├── .env # 환경 변수 파일
├── .gitignore
├── deploy_and_run.sh # 배포 · 실행 스크립트 (cron용)
├── requirements.txt # 의존성 리스트
└── trading_bot/ # 주요 파이썬 모듈
├── init.py
├── account_sync.py # 실계좌 잔고 동기화 헬퍼
├── ai_helpers.py # GPT-4o 관련 헬퍼 (패턴 의사결정, 리플렉션 등)
├── config.py # 설정 및 환경 변수 로드
├── context.py # SignalContext 데이터 클래스
├── data_fetcher.py # OHLCV 데이터 로드(15m/1h) 헬퍼
├── data_io.py # JSON/파일 입출력 헬퍼
├── db_helpers.py # SQLite DB 초기화·로그 기록 헬퍼
├── executor.py # 매매(주문) 실행 및 Discord 알림 로직
├── filters.py # 노이즈 필터링 로직 (룰+AI)
├── indicators_common.py # 15분봉 지표 계산 (SMA/ATR/MACD 등)
├── indicators_1h.py # 1시간봉 지표 계산 (SMA50/EMA/RSI/ATR 등)
├── main.py # 모듈화된 진입점 (python -m trading_bot.main)
├── noise_filters.py # AI 기반 노이즈 감지 헬퍼
├── patterns.py # 룰·AI 복합 패턴 검사 및 매매 의사결정
├── strategies.py # 보조 전략 A/B (볼륨+SMA, EMA 크로스 등)
├── utils.py # 공통 유틸리티 (캐시 로드, 계좌 로드, FNG 등)
├── data/ # 데이터·캐시 폴더
│ ├── ohlcv_cache.json       # 15분봉 OHLCV 캐시 파일
│ ├── fng_cache.json         # Fear & Greed 지수 캐시
│ ├── reflection_cache.json  # AI 반성문 캐시
│ └── trading.db             # SQLite 거래 로그 (indicator_log, trade_log, account 등)
└── logs/ # 자동매매 시 생성되는 로그 파일들
```
---

## 🚀 설치 및 실행

1. **저장소 클론**

    ```bash
    git clone git@github.com:<USERNAME>/gptbitcoin.git
    cd gptbitcoin
    ```

2. **가상환경 생성 및 의존성 설치**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

3. **환경 변수 설정 (`.env` 파일 생성, `.env.sample` 참고)**

    ```
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
    SMA_WINDOW=25
    ATR_WINDOW=16
    VOLUME_SPIKE_THRESHOLD=1.5
    EMA_FAST_WINDOW=12
    EMA_SLOW_WINDOW=26
    RSI_WINDOW=14
    MIN_ORDER_KRW=5000
    CACHE_TTL=3600
    FG_CACHE_TTL=82800
    REFLECTION_INTERVAL_HOURS=11
    REFLECTION_RECURSIVE=true
    REFLECTION_KV_RETRY=2
    BASE_RISK=0.02
    ```

    > ⚠️ **주의:** `.env` 파일에 민감한 API 키를 절대 공개 저장소에 커밋하지 마세요.

    `trading_bot.config` 모듈이 저장소 루트의 `.env` 파일을 자동으로 로드하므로
    크론 작업에서 작업 디렉터리를 별도로 변경할 필요가 없습니다.

4. **데이터베이스 & 캐시 초기화**

    - 첫 실행 시 `trading_bot/config.py` 에서 지정한 경로(기본 `trading_bot/data/trading.db`)에 DB 파일이 자동 생성됩니다.
    - `ohlcv_cache.json`, `fng_cache.json`, `reflection_cache.json` 파일도 같은 폴더에 순차적으로 생성됩니다.

5. **자동매매 스크립트 실행**

    1. **로컬에서 수동 실행**  
       가상환경을 활성화한 상태에서:

       ```bash
       python3 -m trading_bot.main --mode intraday
       ```

       - `--mode intraday` 옵션은 인트라데이(15분봉 + 1시간봉) 모드로 실행합니다.
       - 첫 실행 후 DB(`trading.db`)와 각종 캐시(`ohlcv_cache.json`, `fng_cache.json`, `reflection_cache.json`)가 생성됩니다.
       - 성공적으로 실행되면 콘솔과 `trading_bot/logs/`에 로그가 기록되고,  
         실거래 모드(`LIVE_MODE=true`)에서는 Discord 알림이 발송됩니다.

    2. **배포용 스크립트 사용**  
       리모트 서버(VM)에서는 `deploy_and_run.sh`를 호출하여 한 번에 업데이트 → 설치 → 실행을 할 수 있습니다.

       ```bash
       ./deploy_and_run.sh --mode intraday
       ```

       - **deploy_and_run.sh** 내부:
         ```bash
         #!/usr/bin/env bash
         set -euo pipefail

        # 1) (선택) 리포지토리 최신화
        cd /home/ubuntu/gptbitcoin  # .env 로드를 위한 작업 디렉터리 변경은 필요 없음

         # 2) 가상환경 활성화
         source /home/ubuntu/gptbitcoin/venv/bin/activate

         # 3) 의존성 설치 (필요 시)
         pip install --upgrade pip
         pip install -r requirements.txt

        # 4) 자동매매 스크립트 실행 (인트라데이 모드) & 로그를 trading_bot/logs/cron.log에 덧붙이기
        python3 -m trading_bot.main --mode intraday \
            >> /home/ubuntu/gptbitcoin/trading_bot/logs/cron.log 2>&1
         ```
       
       ⏰ **스케줄링 예시 (cron)**  
       예를 들어, 한국 시간 기준 특정 구간(인트라데이 운영 시간)에 15분마다 실행하도록 설정하려면:

       ```cron
       # ──────────────────────────────────────────────────
       # 한국 시간 02:00~05:59 구간 (UTC 전날 17:00~20:59) 매 15분마다
       */15 17-20 * * * /home/ubuntu/gptbitcoin/deploy_and_run.sh --mode intraday

       # 한국 시간 14:00~17:59 구간 (UTC 당일 05:00~08:59) 매 15분마다
       */15 5-8   * * * /home/ubuntu/gptbitcoin/deploy_and_run.sh --mode intraday
       # ──────────────────────────────────────────────────
       ```

       - 위 예시에서는 `deploy_and_run.sh --mode intraday`를 15분 간격으로 실행하며,
         표준 출력/오류는 `trading_bot/logs/cron.log`에 기록됩니다.

## 🧪 테스트 실행

가상환경을 활성화한 뒤 프로젝트 루트에서 다음 명령으로 단위 테스트를 실행할 수 있습니다.

```bash
python3 -m pytest -q
```

`-q` 옵션은 테스트 결과를 간결하게 출력합니다.
---

## ⚙️ 주요 기능 설명

1. **LIVE / VIRTUAL 모드 분리**  
   - `LIVE_MODE=true`일 때 실제 Upbit 계좌로 시장가 주문을 냅니다.  
   - `LIVE_MODE=false`일 때 가상 계좌(데이터베이스 내 시뮬레이션)만 수행합니다.

2. **잔고 동기화**  
   - `trading_bot/account_sync.py`에서 Upbit API(`Upbit.get_balances`)를 호출해  
     실계좌 KRW, BTC, 평균 매수가를 가져옵니다.

3. **OHLCV 캐시 & REST 백업**
   - `trading_bot/data_fetcher.py`에서
     1) `trading_bot.data_io.load_cached_ohlcv()`로 캐시를 시도하고
     2) 실패 시 `pyupbit.get_ohlcv()` → 백업 REST API(`fetch_direct()`) 순으로 호출합니다.

4. **지표 계산**  
   - **15분봉 지표** (`trading_bot/indicators_common.py`):  
    - SMA(`SMA_WINDOW`), ATR(`ATR_WINDOW`), 20봉 평균 거래량(`vol20`), MACD diff
   - **1시간봉 지표** (`trading_bot/indicators_1h.py`):  
    - SMA50, EMA fast(`EMA_FAST_WINDOW`), EMA slow(`EMA_SLOW_WINDOW`), RSI(`RSI_WINDOW`), ATR(`ATR_WINDOW`)

5. **“Fear & Greed” 지수 (FNG)**  
   - `trading_bot/utils.py` 내 `get_fear_and_greed()`가  
     `alternative.me` API를 호출해 “공포·탐욕 지수”를 가져오고,  
     하루(또는 `FG_CACHE_TTL`초) 동안 캐시로 재사용합니다.

6. **룰 기반 패턴 + AI 보조 패턴**  
   - **`trading_bot/filters.py`**  
     - 최근 5봉 노이즈(이상치) 검사: 볼륨 극단 감소 시 AI(`ask_noise_filter`)에게 물어봅니다.  
   - **`trading_bot/patterns.py`**  
     - **룰 기반 단일/다중 캔들패턴**  
       - 이중바닥·이중천장, 망치형·역망치형·도지 + 볼륨 스파이크 → 매수/매도  
       - Stop‐loss(94% 이하), Take‐profit(5% 이상), Trend‐sell(FNG + MACD)  
      - **AI 복합 패턴**
        - 최근 100봉 데이터를 GPT-4o에 보내 “복합 차트 패턴” 태깅 요청
        - 이미 룰에 정의된 패턴이 아니면 AI에게 “buy/sell/hold” 결정 요청
        - 새로운 패턴은 `trading_bot/data/pattern_history.json`에 기록해 둡니다.
        - 이 과정은 반성문 주기가 도래했을 때만 실행되어 토큰 사용을 최소화합니다.

7. **보조 전략 A / B**  
   - **A. 볼륨 스파이크 + price > SMA30 → 매수 / price < SMA30 → 매도**  
   - **B. EMA(12/26) 골든 크로스 → 매수 / 데드 크로스 → 매도**  
   - 두 보조 전략은 룰·AI 패턴 신호가 없을 때 차례로 동작합니다.

8. **실제 주문 실행 (시장가) + 동적 리스크 관리**  
   - `trading_bot/executor.py`  
     - ATR 기반으로 “포지션 크기”를 1% 리스크 기준으로 동적 계산  
     - 최소 주문액(`MIN_ORDER_KRW`) 미만이면 주문하지 않음  
     - 실거래 모드(`LIVE_MODE=true`)에서는 Upbit 시장가 주문  
     - 가상 모드에서는 DB 계좌에서 가상 계산만 수행

9. **로그 기록 & Discord 알림**
   - `trading_bot/db_helpers.py`
     - SQLite 테이블: `account(id=1)`, `indicator_log`, `trade_log`, `reflection_log` (자동 생성)
   - `trading_bot/executor.py` → `log_and_notify()`
     - 매매 신호를 DB(`trade_log`)에 기록하고,
     - 실제 주문이 체결되었을 때만 Discord Webhook에 알림을 보냅니다.
    - 오래된 로그가 삭제되면 DB를 VACUUM하여 파일 크기를 줄입니다.

10. **AI 반성문 & 전략 자동 조정**
   - 최근 거래 내역과 차트 데이터를 GPT-4o에 보내 간단한 반성문을 생성합니다.
   - 새 반성문은 마지막 작성 이후 `REFLECTION_INTERVAL_HOURS`(기본 11시간) 이상
     지나야만 저장되며, 매매가 없더라도 주기적으로 실행됩니다.

    - 프롬프트는 반드시 `KEY=VALUE` 형식의 전략 조정안을 포함하도록 명시하며,
      이 형식이 감지되면 `.env` 파일에 자동 반영해 전략 수치를 업데이트합니다.
    - 만약 반성문에 `KEY=VALUE` 줄이 없을 경우,
      최소 한 줄을 얻을 때까지 `REFLECTION_KV_RETRY`회(기본 2) 재요청합니다.
      If no KEY=VALUE line is returned even after all retries,
      the bot keeps the existing `.env` values without modification.
      값은 숫자나 `true`/`false` 등 대부분의 기본 타입을 인식합니다.
    - 기본적으로 GPT에게 한 차례 추가 개선을 요청하지만,
      `REFLECTION_RECURSIVE=false`로 설정하면 첫 응답만 사용합니다.


## ❓ 문제 해결 (Troubleshooting)

* **AI 보조 패턴이 항상 'hold'만 반환되는 경우**
  * `OPENAI_API_KEY` 환경 변수가 비어 있거나 잘못되면 `ask_pattern_decision()` 함수가 항상 "hold"를 반환합니다.
* **거래가 발생하지 않는 경우**
  * 1시간봉 SMA50 필터에 걸리면 신호가 무시됩니다.
  * 최근 5봉 거래량이 급감하면 노이즈 감지 로직이 패턴 검사를 중지시킬 수 있습니다.
* **노이즈 필터가 지나치게 자주 발동되는 경우**
  * `NOISE_VOL_THRESHOLD`(룰 기반)과 `AI_NOISE_VOL_THRESHOLD`(AI 기반)은
    최근 4봉 평균 거래량 대비 현재 봉 거래량이 일정 비율 이하로 떨어지면
    매매 시도를 건너뛰도록 합니다. 값이 높을수록 조금만 거래량이 줄어도
    필터가 작동해 잦은 `hold` 상태가 발생할 수 있습니다.
  * `.env`에서 두 값을 더 낮게 조정하면(예: `AI_NOISE_VOL_THRESHOLD=0.05`,
    `NOISE_VOL_THRESHOLD=0.002`) 노이즈로 간주되는 범위가 줄어들어 거래
    빈도가 높아집니다. 상황에 맞게 천천히 값을 조절해 보세요.

## 🛡️ 보안 주의 사항

- `.env` 파일에는 API 키를 절대 공개 저장소에 커밋하지 마세요.
- GitHub 등에는 `.env`를 포함하지 않도록 이미 `.gitignore`에 지정되어 있습니다.
- `requirements.txt`에는 외부 라이브러리 목록만 기록하고, 민감한 정보는 코드 또는 환경 변수로 관리합니다.

---

## 📜 라이선스

이 프로젝트의 저작권은 본인(© KCM)에게 있습니다.  

