# gptbitcoin Trading Bot

자동화된 비트코인 매매 봇입니다. Upbit 현물 마켓을 대상으로 4시간봉 OHLCV 데이터를 기반으로 SMA, ATR, MACD 지표 및 Fear & Greed 지수를 활용하며, 수수료·로그 로테이션·AI 리플렉션 기능을 포함합니다.

## 주요 기능

* LIVE / VIRTUAL 모드 분리 실행
* 잔고 동기화 (Upbit get\_balances + Remaining-Req 파싱 우회)
* OHLCV 캐시 및 REST 백업
* SMA / ATR / MACD 인디케이터 계산
* 공포탐욕 지수(FNG) 일일 캐시
* 수수료(0.05%) 및 양도세(20%) 반영한 익절/손절
* 동적 리스크 캡 (최근 20회 거래 승률 기반)
* 최소 주문액 5,000원, 먼지 제거 로직
* 3MB 로그 로테이션 설정
* GPT-4o 기반 반성 기록(save to DB)

## 설치 및 실행

1. 저장소 클론

   ```bash
   git clone git@github.com:<USERNAME>/gptbitcoin.git
   cd gptbitcoin
   ```

2. 가상환경 생성 및 의존성 설치

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. 환경 변수 설정 (`.env` 파일 생성)

   ```text
   LIVE_MODE=true
   UPBIT_ACCESS_KEY=여기에_업비트_액세스키
   UPBIT_SECRET_KEY=여기에_업비트_시크릿키
   OPENAI_API_KEY=여기에_OpenAI_API_키
   ```

4. 파라미터 파일 생성 (기본값)

   ```json
   {
     "sma": 20,
     "atr": 14,
     "buy_pct": 0.25,
     "sell_pct": 0.50
   }
   ```

5. 자동매매 스크립트 실행

   ```bash
   python autoTrading.py
   ```

## 스케줄링 예시 (cron)

```cron
# 매 4시간마다 실행
0 */4 * * * cd /path/to/gptbitcoin && ./venv/bin/python autoTrading.py >> logs/cron.log 2>&1
```

## 보안 주의 사항

* `.env` 파일에 API 키를 절대 공개 저장소에 커밋하지 마세요.
* `requirements.txt` 에만 라이브러리 목록을 기록합니다.

## 라이선스

MIT © KCM
