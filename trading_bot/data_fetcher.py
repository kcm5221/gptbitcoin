# trading_bot/data_fetcher.py

import pandas as pd
import pyupbit
import logging
from typing import Optional

from trading_bot.data_io import load_cached_ohlcv, save_cached_ohlcv, safe_ohlcv, fetch_ohlcv_1h

logger = logging.getLogger(__name__)


def fetch_data_15m() -> pd.DataFrame:
    """
    15분봉 OHLCV 데이터 로드 (캐시 → 백업 API)
    """
    df = load_cached_ohlcv()
    if df is None or df.empty:
        df = safe_ohlcv()
    if df is None or df.empty:
        raise RuntimeError("OHLCV 데이터 로딩 실패 (15분봉)")
    return df


def fetch_data_1h(ticker: str, count: int = 100) -> Optional[pd.DataFrame]:
    """
    1시간봉 OHLCV 데이터 로드 (pyupbit.get_ohlcv 사용)
    """
    return fetch_ohlcv_1h(ticker, count)
