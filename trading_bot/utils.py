# trading_bot/utils.py

import json
import logging
import os
import sqlite3
import time
from typing import Any, Callable, Optional, Dict, List

import numpy as np
import pandas as pd
import pyupbit
import requests
from openai import OpenAI

from trading_bot.config import (
    DB_FILE,
    CACHE_FILE,
    CACHE_TTL,
    MIN_ORDER_KRW,
    TICKER,
    INTERVAL,
    PLAY_RATIO,
    RESERVE_RATIO,
    FG_CACHE_TTL,
    SMA_WIN,
    ATR_WIN,
    PATTERN_HISTORY_FILE,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# “Fear & Greed” 지수 캐시
# ──────────────────────────────────────────────────────────────
FNG_CACHE: Dict[str, Any] = {"ts": 0, "value": None}

def get_fear_and_greed() -> Optional[int]:
    """
    alternative.me API를 통해 Fear & Greed 지수를 가져와서,
    캐시 유효기간(FG_CACHE_TTL) 동안 재사용.
    """
    if time.time() - FNG_CACHE["ts"] < FG_CACHE_TTL and FNG_CACHE["value"] is not None:
        return FNG_CACHE["value"]

    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return FNG_CACHE["value"]
        val_str = data[0].get("value")
        if val_str is None:
            return FNG_CACHE["value"]
        val = int(val_str)
        FNG_CACHE.update(ts=time.time(), value=val)
        return val
    except Exception as e:
        logger.warning("get_fear_and_greed() 실패: %s", e)
        return FNG_CACHE["value"]

# ──────────────────────────────────────────────────────────────
# DB 헬퍼: 초기화, 로드, 저장, 로깅
# ──────────────────────────────────────────────────────────────
def with_db(fn: Callable[..., Any]):
    """
    SQLite 데이터베이스 연결을 자동으로 열고 닫아 주는 데코레이터.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        try:
            result = fn(conn, *args, **kwargs)
            conn.commit()
            return result
        finally:
            conn.close()
    return wrapper

@with_db
def init_db(conn: sqlite3.Connection) -> None:
    """
    DB 파일이 없으면 생성하고, 필요한 테이블을 만든다.
    """
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS account (
      id INTEGER PRIMARY KEY CHECK(id=1),
      krw REAL,
      btc REAL,
      avg_price REAL
    );
    CREATE TABLE IF NOT EXISTS indicator_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts REAL,
      sma REAL,
      atr REAL,
      vol20 REAL,
      macd_diff REAL,
      price REAL,
      fear_greed INTEGER
    );
    CREATE TABLE IF NOT EXISTS trade_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts REAL,
      decision TEXT,
      percentage REAL,
      pattern TEXT,
      reason TEXT,
      btc_balance REAL,
      krw_balance REAL,
      avg_price REAL,
      price REAL,
      mode TEXT,
      reflection TEXT
    );
    """)

@with_db
def load_account(conn: sqlite3.Connection) -> tuple[float, float, float]:
    """
    account 테이블에서 잔고(krw, btc, avg_price)를 불러온다.
    없으면 초기값(30000,0,0)을 삽입 후 리턴.
    """
    row = conn.execute("SELECT krw, btc, avg_price FROM account WHERE id=1").fetchone()
    if row:
        return row["krw"], row["btc"], row["avg_price"]
    conn.execute("INSERT INTO account VALUES(1, 30000, 0, 0)")
    return 30000.0, 0.0, 0.0

@with_db
def save_account(conn: sqlite3.Connection, krw: float, btc: float, avg_price: float) -> None:
    """
    현재 account 값을 DB에 업데이트.
    """
    conn.execute(
        "UPDATE account SET krw=?, btc=?, avg_price=? WHERE id=1",
        (krw, btc, avg_price)
    )

@with_db
def log_indicator(conn: sqlite3.Connection, ts: float, sma: float, atr: float,
                  vol20: float, macd_diff: float, price: float, fear_greed: int) -> None:
    """
    매 호출 시점의 지표를 indicator_log 테이블에 기록.
    """
    conn.execute(
        """INSERT INTO indicator_log
           (ts, sma, atr, vol20, macd_diff, price, fear_greed)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ts, sma, atr, vol20, macd_diff, price, fear_greed)
    )

@with_db
def log_trade(conn: sqlite3.Connection, ts: float, decision: str, percentage: float,
              pattern: str, reason: str, btc_balance: float, krw_balance: float,
              avg_price: float, price: float, mode: str, reflection: str) -> None:
    """
    매매가 이루어질 때마다 trade_log 테이블에 기록.
    """
    conn.execute(
        """INSERT INTO trade_log
           (ts, decision, percentage, pattern, reason,
            btc_balance, krw_balance, avg_price, price, mode, reflection)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ts, decision, percentage, pattern, reason,
         btc_balance, krw_balance, avg_price, price, mode, reflection)
    )

def get_recent_trades(limit: int = 20) -> pd.DataFrame:
    """
    trade_log 테이블에서 최근 limit개 행을 DataFrame으로 반환.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT ts, decision, percentage, reason, btc_balance, krw_balance, avg_price, price "
        "FROM trade_log ORDER BY ts DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    cols = [col[0] for col in cur.description]
    conn.close()
    return pd.DataFrame(rows, columns=cols)

# ──────────────────────────────────────────────────────────────
# Upbit 실계좌 잔고 동기화 함수
# ──────────────────────────────────────────────────────────────
def sync_account_upbit() -> tuple[float, float, float]:
    """
    Upbit 실계좌에서 잔고(krw, btc, avg_price)를 가져옴.
    인증 오류 등 발생 시 (0,0,0) 리턴.
    """
    try:
        upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", ""))
        bal = upbit.get_balances()
        if isinstance(bal, dict) and "error" in bal:
            raise RuntimeError(bal["error"]["message"])
        def _get_balance(cur: str, f: str = "balance") -> float:
            raw = next((b.get(f, "0") for b in bal if b["currency"] == cur), "0")
            return float(raw or 0.0)

        return _get_balance("KRW"), _get_balance("BTC"), _get_balance("BTC", "avg_buy_price")
    except Exception as e:
        logger.warning("sync_account_upbit() 실패: %s", e)
        return 0.0, 0.0, 0.0

# ──────────────────────────────────────────────────────────────
# OpenAI GPT-4o 반성 일기
# ──────────────────────────────────────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
client     = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def ask_ai_reflection(df: pd.DataFrame, fear_idx: int) -> Optional[str]:
    """
    최근 trade_log 20건과 fear_idx를 GPT-4o 모델에 넘겨서
    120 토큰 이내 분량의 “반성 일기”를 받아옴.
    """
    if client is None:
        return None
    prompt = (
        "You are a crypto trading coach.\n"
        f"Recent trades: {df.to_json(orient='records')}\n"
        f"Fear-Greed index={fear_idx}\n"
        "Respond in ≤120 words: what worked, what didn't, one improvement."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("ask_ai_reflection() 실패: %s", e)
        return None

# ──────────────────────────────────────────────────────────────
# OHLCV 캐시·로딩 & 지표 계산 (15분봉)
# ──────────────────────────────────────────────────────────────
def load_cached_ohlcv() -> Optional[pd.DataFrame]:
    """
    CACHE_FILE에 JSON 캐시가 있으면 읽어서 DataFrame으로 반환.
    TTL(CACHE_TTL)을 벗어나면 None 반환하여 새로 fetch하게 유도.
    """
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        raw = json.loads(open(CACHE_FILE, "r", encoding="utf-8").read())
        if time.time() - raw["ts"] > CACHE_TTL:
            return None
        df = pd.DataFrame(raw["ohlcv"])
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        os.remove(CACHE_FILE)
        return None

def save_cached_ohlcv(df: pd.DataFrame) -> None:
    """
    현재 DataFrame(ohlcv)을 JSON으로 캐시에 저장.
    index를 문자열로 전환해서 JSON 직렬화가 가능하도록 함.
    """
    cp = df.copy()
    cp.index = cp.index.astype(str)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "ohlcv": cp.to_dict()}, f)

def fetch_direct() -> Optional[pd.DataFrame]:
    """
    Upbit REST API(15분봉)로 직접 데이터를 가져오는 백업 함수.
    - count=100 으로 최근 100봉.
    """
    try:
        unit = INTERVAL.replace("minute", "")
        url = f"https://api.upbit.com/v1/candles/minutes/{unit}"
        resp = requests.get(url, params={"market": TICKER, "count": 100}, timeout=5)
        resp.raise_for_status()
        data = resp.json()[::-1]
        df = pd.DataFrame(data).rename(columns={
            "opening_price": "open",
            "high_price":    "high",
            "low_price":     "low",
            "trade_price":   "close",
            "candle_acc_trade_volume": "volume",
        })
        df.index = pd.to_datetime(df["candle_date_time_kst"])
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.warning("fetch_direct() 실패: %s", e)
        return None

def safe_ohlcv() -> Optional[pd.DataFrame]:
    """
    pyupbit.get_ohlcv() → 실패 시 fetch_direct() 로 백업
    """
    try:
        df = pyupbit.get_ohlcv(TICKER, count=100, interval=INTERVAL)
        if df is None or df.empty:
            raise RuntimeError("pyupbit.get_ohlcv 빈 데이터")
        return df
    except Exception as e:
        logger.warning("pyupbit.get_ohlcv 에러: %s, fetch_direct 시도", e)
        return fetch_direct()

def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame에 SMA, ATR, vol20, MACD diff 컬럼을 추가하여 반환.
    (15분봉용)
    """
    from ta.trend import SMAIndicator, MACD
    from ta.volatility import AverageTrueRange
    from ta.utils import dropna

    df = dropna(df.copy())
    df["sma"]      = SMAIndicator(df["close"], SMA_WIN, fillna=True).sma_indicator()
    df["atr"]      = AverageTrueRange(df["high"], df["low"], df["close"], ATR_WIN, fillna=True).average_true_range()
    df["vol20"]    = df["volume"].rolling(20).mean()
    df["macd_diff"]= MACD(df["close"], fillna=True).macd_diff()
    return df
