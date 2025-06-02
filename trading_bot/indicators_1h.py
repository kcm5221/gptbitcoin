# trading_bot/indicators_1h.py

import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from trading_bot.config import EMA_FAST_WINDOW, EMA_SLOW_WINDOW, RSI_WINDOW, ATR_WIN

def calc_indicators_1h(df: pd.DataFrame) -> pd.DataFrame:
    """
    1시간봉 지표 계산:
      - SMA(50)  (예: 50시간 이동평균)
      - EMA(FAST=EMA_FAST_WINDOW, SLOW=EMA_SLOW_WINDOW)
      - RSI(RSI_WINDOW)
      - ATR(ATR_WIN)
    """
    df = df.dropna().copy()
    df["sma50_1h"]    = SMAIndicator(df["close"], window=50, fillna=True).sma_indicator()
    df["ema_fast_1h"] = EMAIndicator(df["close"], window=EMA_FAST_WINDOW, fillna=True).ema_indicator()
    df["ema_slow_1h"] = EMAIndicator(df["close"], window=EMA_SLOW_WINDOW, fillna=True).ema_indicator()
    df["rsi_1h"]      = RSIIndicator(df["close"], window=RSI_WINDOW, fillna=True).rsi()
    df["atr_1h"]      = AverageTrueRange(df["high"], df["low"], df["close"], window=ATR_WIN, fillna=True).average_true_range()
    return df
