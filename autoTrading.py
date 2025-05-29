#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autoTrading.py
LIVE / VIRTUAL 자동매매
- 3 MB 로그 로테이션
- get_balances 잔고 동기화 + Remaining-Req 우회
- OHLCV 캐시 · REST 백업, SMA/ATR/MACD, Fear-Greed(일일 캐시)
- 가격 기반 익절(+5 %) / 손절(–6 %) 우선 매도
- 동적 Risk, 먼지 간주(5 000원 미만), 최소주문 5 000원
- GPT-4o reflection 저장
- 에러 발생 시 Discord 알림
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sqlite3
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Optional

import pandas as pd
import pyupbit
import requests
from dotenv import load_dotenv
from openai import OpenAI
from ta.trend import SMAIndicator, MACD
from ta.utils import dropna
from ta.volatility import AverageTrueRange

# Remaining-Req 파싱 무시용 패치
import pyupbit.request_api as _rq  # noqa: E402


def _ignore_remaining_req(headers: Any) -> tuple[int, int, int]:
    return 0, 0, 0


_rq._parse = _ignore_remaining_req  # noqa: E402

# ──────────────────────────────────────────────────────────────
# 환경
# ──────────────────────────────────────────────────────────────
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

TICKER = "KRW-BTC"
INTERVAL = "minute240"
CACHE_TTL = 3600
DB_FILE = "trading.db"
CACHE_FILE = "ohlcv_cache.json"
MIN_ORDER_KRW = 5_000

ACCESS = os.getenv("UPBIT_ACCESS_KEY", "").strip()
SECRET = os.getenv("UPBIT_SECRET_KEY", "").strip()
LIVE_MODE = (
    os.getenv("LIVE_MODE", "false").lower() == "true"
    and ACCESS
    and SECRET
)
UPBIT = pyupbit.Upbit(ACCESS, SECRET) if LIVE_MODE else None

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")


# ──────────────────────────────────────────────────────────────
# Discord Notify
# ──────────────────────────────────────────────────────────────
def notify_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=5)
    except Exception as e:
        logger.warning("Discord notify failed – %s", e)


# ───────── 로그: 3MB 회전 ─────────
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
handler = RotatingFileHandler(
    LOG_DIR / "trade.log",
    maxBytes=3_000_000,
    backupCount=5,
    encoding="utf-8",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[handler, logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
logger.info("MODE: %s", "LIVE" if LIVE_MODE else "VIRTUAL")

# ──────────────────────────────────────────────────────────────
# 전략 파라미터
# ──────────────────────────────────────────────────────────────
param_file = PROJECT_ROOT / "optimize" / "best_params.json"
if param_file.exists():
    p = json.load(param_file.open())
    SMA_WIN = p.get("sma", 30)
    ATR_WIN = p.get("atr", 14)
    BUY_PCT = 0.25
    SELL_PCT = p.get("sell_pct", 0.50)
else:
    SMA_WIN, ATR_WIN, BUY_PCT, SELL_PCT = 30, 14, 0.25, 0.50

FG_BUY_TH = 40
FG_SELL_TH = 70
BASE_RISK = 0.02

# ──────────────────────────────────────────────────────────────
# FNG 일일 캐시
# ──────────────────────────────────────────────────────────────
FNG_CACHE: dict[str, Any] = {"ts": 0, "value": None}


def get_fear_and_greed() -> Optional[int]:
    if time.time() - FNG_CACHE["ts"] < 82_800 and FNG_CACHE["value"] is not None:
        return FNG_CACHE["value"]
    try:
        val = int(
            requests.get(
                "https://api.alternative.me/fng/?limit=1", timeout=10
            ).json()["data"][0]["value"]
        )
        FNG_CACHE.update(ts=time.time(), value=val)
        return val
    except Exception as e:
        logger.warning("FG fetch fail – %s", e)
        return FNG_CACHE["value"]


# ──────────────────────────────────────────────────────────────
# DB Helper
# ──────────────────────────────────────────────────────────────
@dataclass
class Account:
    krw: float
    btc: float
    avg_price: float


def with_db(fn: Callable[..., Any]):
    def wrapper(*args: Any, **kw: Any) -> Any:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            return fn(conn, *args, **kw)
    return wrapper


@with_db
def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS account(
      id INTEGER PRIMARY KEY CHECK(id=1),
      krw REAL, btc REAL, avg_price REAL
    );
    CREATE TABLE IF NOT EXISTS indicator_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts REAL, sma REAL, atr REAL, vol20 REAL,
      macd_diff REAL, price REAL, fear_greed INTEGER
    );
    CREATE TABLE IF NOT EXISTS trade_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts REAL, decision TEXT, percentage REAL, pattern TEXT, reason TEXT,
      btc_balance REAL, krw_balance REAL, avg_price REAL, price REAL,
      mode TEXT, reflection TEXT
    );
    """)


@with_db
def load_account(conn: sqlite3.Connection) -> Account:
    row = conn.execute(
        "SELECT krw, btc, avg_price FROM account WHERE id=1"
    ).fetchone()
    if row:
        return Account(**row)
    conn.execute("INSERT INTO account VALUES(1, 30000, 0, 0)")
    return Account(30000, 0, 0)


@with_db
def save_account(conn: sqlite3.Connection, acc: Account) -> None:
    conn.execute(
        "UPDATE account SET krw=?, btc=?, avg_price=? WHERE id=1",
        (acc.krw, acc.btc, acc.avg_price),
    )


@with_db
def log_indicator(conn: sqlite3.Connection, d: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO indicator_log
        (ts, sma, atr, vol20, macd_diff, price, fear_greed)
        VALUES(:ts, :sma, :atr, :vol20, :macd_diff, :price, :fear_greed)""",
        d,
    )


@with_db
def log_trade(conn: sqlite3.Connection, d: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO trade_log
        (ts, decision, percentage, pattern, reason,
         btc_balance, krw_balance, avg_price, price, mode, reflection)
        VALUES(:ts, :decision, :percentage, :pattern, :reason,
               :btc_balance, :krw_balance, :avg_price, :price, :mode, :reflection)""",
        d,
    )


def get_recent_trades(limit: int = 20) -> pd.DataFrame:
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute(
            "SELECT ts, decision, percentage, reason, btc_balance, "
            "krw_balance, avg_price, price "
            "FROM trade_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
    return pd.DataFrame(rows, columns=cols)


# ──────────────────────────────────────────────────────────────
# OHLCV & 지표
# ──────────────────────────────────────────────────────────────
def load_cached_ohlcv() -> Optional[pd.DataFrame]:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        raw = json.load(open(CACHE_FILE))
        if time.time() - raw["ts"] > CACHE_TTL:
            return None
        df = pd.DataFrame(raw["ohlcv"])
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        os.remove(CACHE_FILE)
        return None


def save_cached_ohlcv(df: pd.DataFrame) -> None:
    cp = df.copy()
    cp.index = cp.index.astype(str)
    json.dump({"ts": time.time(), "ohlcv": cp.to_dict()},
              open(CACHE_FILE, "w"))


def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = dropna(df)
    df["sma"] = SMAIndicator(df["close"], SMA_WIN, True).sma_indicator()
    df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"],
                                 ATR_WIN, True).average_true_range()
    df["vol20"] = df["volume"].rolling(20).mean()
    df["macd_diff"] = MACD(df["close"], fillna=True).macd_diff()
    return df


def fetch_direct() -> Optional[pd.DataFrame]:
    unit = INTERVAL.replace("minute", "")
    r = requests.get(
        f"https://api.upbit.com/v1/candles/minutes/{unit}",
        params={"market": TICKER, "count": 100},
        timeout=5,
    )
    if r.status_code != 200:
        return None
    data = r.json()[::-1]
    df = pd.DataFrame(data).rename(columns={
        "opening_price": "open",
        "high_price": "high",
        "low_price": "low",
        "trade_price": "close",
        "candle_acc_trade_volume": "volume",
    })
    df.index = pd.to_datetime(df["candle_date_time_kst"])
    return df[["open", "high", "low", "close", "volume"]]


def safe_ohlcv() -> Optional[pd.DataFrame]:
    try:
        df = pyupbit.get_ohlcv(TICKER, count=100, interval=INTERVAL)
    except Exception as e:
        logger.warning("pyupbit error %s", e)
        df = None
    if df is not None and not df.empty:
        return df
    return fetch_direct()


# ──────────────────────────────────────────────────────────────
# 잔고 동기화
# ──────────────────────────────────────────────────────────────
def sync_account_upbit() -> Account:
    try:
        bal = UPBIT.get_balances()

        if isinstance(bal, dict) and "error" in bal:
            raise RuntimeError(bal["error"]["message"])

        def _get_balance(cur: str, f: str = "balance") -> float:
            """잔고 딕셔너리에서 currency == cur 인 값의 필드 f 를 float 로 반환"""
            raw = next((b.get(f, "0") for b in bal if b["currency"] == cur), "0")
            return float(raw or 0)
        return Account(
            _get_balance("KRW"),
            _get_balance("BTC"),
            _get_balance("BTC", "avg_buy_price"),
        )
    except Exception as e:
        logger.warning("balance sync error – %s", e)
        return Account(0, 0, 0)


# ──────────────────────────────────────────────────────────────
# GPT-4o reflection
# ──────────────────────────────────────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def ask_ai_reflection(df: pd.DataFrame, fear_idx: int) -> Optional[str]:
    if not client:
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
        logger.warning("OpenAI reflection error – %s", e)
        return None


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
def ai_trading() -> None:
    try:
        init_db()
        acc = sync_account_upbit() if LIVE_MODE else load_account()

        df = load_cached_ohlcv()
        if df is None or df.empty:
            df = safe_ohlcv()
        if df is None or df.empty:
            logger.error("OHLCV fetch failed")
            return

        save_cached_ohlcv(df)
        df = calc_indicators(df)
        last = df.iloc[-1]
        ts_end = last.name.floor("4h")

        if sqlite3.connect(DB_FILE).execute(
            "SELECT 1 FROM indicator_log WHERE ts>=?",
            (ts_end.timestamp(),),
        ).fetchone():
            logger.info("Candle %s already processed", ts_end)
            return

        fear = get_fear_and_greed() or 0
        price = float(last["close"])
        macd = float(last["macd_diff"])

        # 먼지 간주
        if acc.btc * price < MIN_ORDER_KRW:
            acc.btc = 0
            acc.avg_price = 0

        # 매수·매도 판단
        buy = price > last.sma and fear < FG_BUY_TH
        stop_loss = acc.btc > 0 and price <= acc.avg_price * 0.94
        FEE = 0.0005
        effective_target = (1 + FEE) * 1.05 / (1 - FEE)
        take_profit = price >= acc.avg_price * effective_target
        trend_sell = acc.btc > 0 and fear >= FG_SELL_TH and macd < 0
        sell = stop_loss or take_profit or trend_sell

        if buy:
            decision, pct, reason = "buy", BUY_PCT * 100, "Price>SMA & FG<40"
        elif sell:
            decision, pct = "sell", 100.0
            reason = (
                "Stop-loss −6%" if stop_loss else
                "Take-profit +5%" if take_profit else
                "FG>=70 & MACD<0"
            )
        else:
            decision, pct, reason = "hold", 0, "No signal"

        if buy and acc.krw < MIN_ORDER_KRW * 2:
            pct = 100.0

        rows = sqlite3.connect(DB_FILE).execute(
            "SELECT decision,percentage FROM trade_log "
            "ORDER BY id DESC LIMIT 20"
        ).fetchall()
        wins = sum(1 for d, p in rows if d == "buy" and p > 0)
        win_rate = wins / len(rows) if rows else 0.5
        dyn_cap = (
            BUY_PCT if len(rows) < 5 else
            0.005 if win_rate < 0.4 else
            0.015 if win_rate < 0.6 else
            BASE_RISK
        )
        if decision == "buy":
            pct = min(pct, dyn_cap * 100)

        krw, btc, avg = acc.krw, acc.btc, acc.avg_price
        executed = False

        if decision == "buy" and pct > 0:
            amt = krw * pct / 100
            if not (LIVE_MODE and amt < MIN_ORDER_KRW):
                executed = True
                if LIVE_MODE:
                    UPBIT.buy_market_order(TICKER, amt)
                else:
                    qty = amt / price
                    krw -= amt
                    btc += qty
                    avg = (avg * acc.btc + amt) / btc if btc else price

        elif decision == "sell" and btc > 0:
            qty = btc * pct / 100
            value = qty * price
            if not (LIVE_MODE and value < MIN_ORDER_KRW):
                executed = True
                if LIVE_MODE:
                    UPBIT.sell_market_order(TICKER, qty)
                else:
                    krw += value
                    btc -= qty

        if LIVE_MODE and executed:
            acc = sync_account_upbit()
            krw, btc, avg = acc.krw, acc.btc, acc.avg_price

        reflection = ask_ai_reflection(get_recent_trades(20), fear) or ""

        save_account(Account(krw, btc, avg))
        ts = time.time()
        log_indicator({
            "ts": ts, "sma": float(last["sma"]), "atr": float(
                last["atr"]
            ), "vol20": float(last["vol20"]), "macd_diff": macd,
            "price": price, "fear_greed": fear
        })
        log_trade({
            "ts": ts, "decision": decision, "percentage": pct,
            "pattern": None, "reason": reason,
            "btc_balance": btc, "krw_balance": krw,
            "avg_price": avg, "price": price,
            "mode": "live" if LIVE_MODE else "virtual",
            "reflection": reflection
        })

        logger.info(
            "Executed=%s pct=%.2f mode=%s",
            executed, pct, "live" if LIVE_MODE else "virtual"
        )

        msg = (
            f"� 자동매매 결과: **{decision.upper()}**\n"
            f"- 비중: {pct:.2f}%\n"
            f"- 가격: {price:.0f} KRW\n"
            f"- KRW 잔고: {krw:.0f}\n"
            f"- BTC 잔고: {btc:.6f}\n"
        )
        notify_discord(msg)

    except Exception as e:
        logger.error("ai_trading() 에러 – %s", e, exc_info=True)
        notify_discord(f":x: 자동매매 중 예외 발생: `{e}`")


if __name__ == "__main__":
    try:
        ai_trading()
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
    except Exception as e:
        logger.error("Unexpected error – %s", e, exc_info=True)
        notify_discord(f":bangbang: 자동매매 스크립트 장애: `{e}`")
