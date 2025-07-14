# trading_bot/indicators_common.py

import pandas as pd
from ta.trend import SMAIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.utils import dropna
import logging

from trading_bot.config import SMA_WINDOW, ATR_WINDOW

logger = logging.getLogger(__name__)

def calc_indicators_15m(df: pd.DataFrame) -> pd.DataFrame:
    """
    15분봉 지표 계산:
      - SMA (window = SMA_WINDOW)
      - ATR (window = ATR_WINDOW)
      - vol20 (20봉 이동평균 거래량)
      - MACD diff
    """
    try:
        # NaN 제거 및 복사
        df2 = dropna(df.copy())

        # (1) SMA
        df2["sma"] = SMAIndicator(
            close=df2["close"], window=SMA_WINDOW, fillna=True
        ).sma_indicator()

        # (2) ATR
        df2["atr"] = AverageTrueRange(
            high=df2["high"],
            low=df2["low"],
            close=df2["close"],
            window=ATR_WINDOW,
            fillna=True
        ).average_true_range()

        # (3) 20봉 평균 거래량
        df2["vol20"] = df2["volume"].rolling(window=20).mean()

        # (4) MACD diff
        df2["macd_diff"] = MACD(df2["close"], fillna=True).macd_diff()

        return df2

    except Exception as e:
        logger.exception(f"calc_indicators_15m() 예외 발생: {e}")
        # 최소한 원본 df에 필수 컬럼이 없으면 빈 DF 반환
        return pd.DataFrame()

