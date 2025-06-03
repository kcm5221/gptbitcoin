import pandas as pd
import logging

from ta.trend import SMAIndicator, EMAIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
from ta.utils import dropna

from trading_bot.config import EMA_FAST_WINDOW, EMA_SLOW_WINDOW, RSI_WINDOW, ATR_WINDOW

logger = logging.getLogger(__name__)


def calc_indicators_1h(df: pd.DataFrame) -> pd.DataFrame:
    """
    1시간봉 지표 계산:
      - SMA50 (고정값)
      - EMA fast/slow (윈도우는 EMA_FAST_WINDOW, EMA_SLOW_WINDOW)
      - RSI (윈도우는 RSI_WINDOW)
      - ATR (윈도우는 ATR_WINDOW)
      - MACD diff를 계산하려면 MACDIndicator를 import하거나 직접 계산
    """
    try:
        df2 = dropna(df.copy())

        # (1) 1시간봉 SMA50
        df2["sma50_1h"] = SMAIndicator(
            close=df2["close"],
            window=50,    # 고정값 50봉
            fillna=True
        ).sma_indicator()

        # (2) EMA fast / slow
        df2["ema_fast_1h"] = EMAIndicator(
            close=df2["close"],
            window=EMA_FAST_WINDOW,
            fillna=True
        ).ema_indicator()
        df2["ema_slow_1h"] = EMAIndicator(
            close=df2["close"],
            window=EMA_SLOW_WINDOW,
            fillna=True
        ).ema_indicator()

        # (3) RSI
        df2["rsi_1h"] = RSIIndicator(
            close=df2["close"],
            window=RSI_WINDOW,
            fillna=True
        ).rsi()

        # (4) ATR
        df2["atr_1h"] = AverageTrueRange(
            high=df2["high"],
            low=df2["low"],
            close=df2["close"],
            window=ATR_WINDOW,
            fillna=True
        ).average_true_range()

        # (5) MACD diff 계산 (EMAfast - EMAslow)
        #    pandas 또는 ta 라이브러리에서 MACD diff를 계산해도 무방
        #    여기서는 간단히 직접 계산 예시:
        df2["macd_diff_1h"] = df2["ema_fast_1h"] - df2["ema_slow_1h"]

        return df2

    except Exception as e:
        logger.exception(f"calc_indicators_1h() 예외 발생: {e}")
        return pd.DataFrame()
