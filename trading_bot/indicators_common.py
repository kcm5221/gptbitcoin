# trading_bot/indicators_common.py

import pandas as pd
from ta.trend import SMAIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.utils import dropna

from trading_bot.config import SMA_WIN, ATR_WIN

def calc_indicators_15m(df: pd.DataFrame) -> pd.DataFrame:
    """
    15분봉 지표 계산:
      - SMA(SMA_WIN)
      - ATR(ATR_WIN)
      - vol20 (20봉 이동평균 거래량)
      - MACD diff
    """
    df = dropna(df.copy())
    df["sma"]      = SMAIndicator(df["close"], SMA_WIN, fillna=True).sma_indicator()
    df["atr"]      = AverageTrueRange(df["high"], df["low"], df["close"], ATR_WIN, fillna=True).average_true_range()
    df["vol20"]    = df["volume"].rolling(20).mean()
    df["macd_diff"]= MACD(df["close"], fillna=True).macd_diff()
    return df
