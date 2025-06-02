# trading_bot/data_io.py

import json
import os
import time
import logging
from typing import Optional

import pandas as pd
import pyupbit
import requests

from trading_bot.config import TICKER, INTERVAL, CACHE_FILE, CACHE_TTL

logger = logging.getLogger(__name__)


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


def fetch_ohlcv_1h(ticker: str, count: int = 100) -> Optional[pd.DataFrame]:
    """
    Upbit API 또는 pyupbit를 이용해서 1시간봉 데이터를 가져오고,
    DataFrame으로 반환합니다. 최대 count개 (기본 100개).
    """
    try:
        df = pyupbit.get_ohlcv(ticker, interval="minute60", count=count)
        if df is None or df.empty:
            raise RuntimeError("pyupbit.get_ohlcv(1h) returned empty DataFrame")
        return df
    except Exception as e:
        logger.warning("fetch_ohlcv_1h() 실패: %s", e)
        return None
