# trading_bot/data_fetcher.py

import pandas as pd
import logging
from typing import Optional

import pyupbit
import requests
from trading_bot.data_io import (
    load_cached_ohlcv,
    save_cached_ohlcv,
)
from trading_bot.config import TICKER, INTERVAL

logger = logging.getLogger(__name__)


def fetch_direct() -> Optional[pd.DataFrame]:
    """Upbit REST API(15분봉)로 데이터를 가져오는 백업 함수."""
    try:
        unit = INTERVAL.replace("minute", "")
        url = f"https://api.upbit.com/v1/candles/minutes/{unit}"
        resp = requests.get(url, params={"market": TICKER, "count": 100}, timeout=5)
        resp.raise_for_status()
        data = resp.json()[::-1]
        df = pd.DataFrame(data).rename(columns={
            "opening_price": "open",
            "high_price": "high",
            "low_price": "low",
            "trade_price": "close",
            "candle_acc_trade_volume": "volume",
        })
        df.index = pd.to_datetime(df["candle_date_time_kst"], errors="coerce")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        logger.exception("fetch_direct() 실패")
        return None


def safe_ohlcv() -> Optional[pd.DataFrame]:
    """pyupbit.get_ohlcv() 실패 시 fetch_direct()로 백업."""
    try:
        df = pyupbit.get_ohlcv(TICKER, count=100, interval=INTERVAL)
        if df is None or df.empty:
            raise RuntimeError("pyupbit.get_ohlcv 빈 데이터")
        return df
    except Exception:
        logger.warning("pyupbit.get_ohlcv 에러 발생, fetch_direct 시도")
        return fetch_direct()


def fetch_ohlcv_1h_via_rest(ticker: str, count: int = 100) -> Optional[pd.DataFrame]:
    """Upbit REST API(1시간봉)로 데이터를 가져오는 백업 함수."""
    try:
        url = "https://api.upbit.com/v1/candles/minutes/60"
        resp = requests.get(url, params={"market": ticker, "count": count}, timeout=5)
        resp.raise_for_status()
        data = resp.json()[::-1]
        df = pd.DataFrame(data).rename(columns={
            "opening_price": "open",
            "high_price": "high",
            "low_price": "low",
            "trade_price": "close",
            "candle_acc_trade_volume": "volume",
        })
        df.index = pd.to_datetime(df["candle_date_time_kst"], errors="coerce")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        logger.exception("fetch_ohlcv_1h_via_rest() 실패")
        return None

def fetch_data_15m() -> Optional[pd.DataFrame]:
    """
    15분봉 OHLCV 데이터 로드 (캐시 → 백업 API).
    실패 시 None 반환.
    """
    try:
        # 1) 캐시 시도
        df = load_cached_ohlcv()
        if df is not None and not df.empty:
            return df

        # 2) pyupbit → fetch_direct 순으로 시도
        df = safe_ohlcv()
        if df is not None and not df.empty:
            try:
                # 캐시에 저장해 두면 다음 호출 시 빠름
                save_cached_ohlcv(df)
            except Exception:
                logger.exception("save_cached_ohlcv() 중 예외 발생(무시)")
            return df

        # 3) 모든 시도 실패
        logger.error("fetch_data_15m: 모든 데이터 소스 실패, None 반환")
        return None

    except Exception as e:
        logger.exception(f"fetch_data_15m() 예외 발생: {e}")
        return None


def fetch_data_1h(ticker: str, count: int = 100) -> Optional[pd.DataFrame]:
    """
    1시간봉 OHLCV 데이터 로드 (pyupbit.get_ohlcv 사용).
    실패 시 None 반환.
    """
    try:
        df = pyupbit.get_ohlcv(ticker, interval="minute60", count=count)
        if df is None or df.empty:
            raise RuntimeError("pyupbit.get_ohlcv 빈 데이터")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        logger.warning("pyupbit.get_ohlcv 실패 → REST 백업 시도")
        try:
            df = fetch_ohlcv_1h_via_rest(ticker, count)
            if df is not None and not df.empty:
                return df
        except Exception:
            logger.exception("fetch_ohlcv_1h_via_rest 실패")

        logger.error("fetch_data_1h: 데이터 없음, None 반환")
        return None
