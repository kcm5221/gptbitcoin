# trading_bot/data_fetcher.py

import pandas as pd
import logging
from typing import Optional

from trading_bot.data_io import load_cached_ohlcv, save_cached_ohlcv, safe_ohlcv, fetch_direct

logger = logging.getLogger(__name__)

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
        df = fetch_direct()  # fetch_direct 내부에서 pyupbit도 호출함
        if df is not None and not df.empty:
            return df

        logger.error("fetch_data_1h: 데이터 없음, None 반환")
        return None

    except Exception as e:
        logger.exception(f"fetch_data_1h() 예외 발생: {e}")
        return None
