# trading_bot/indicators.py

import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
from ta.utils import dropna

from trading_bot.config import SMA_WIN, ATR_WIN, EMA_FAST_WINDOW, EMA_SLOW_WINDOW, RSI_WINDOW

def calc_indicators_15m(df: pd.DataFrame) -> pd.DataFrame:
    """
    15분봉 지표 계산:
      - SMA(SMA_WIN)
      - ATR(ATR_WIN)
      - vol20 (20봉 이동평균 거래량)
      - MACD diff
    """
    # 원본 DataFrame 건드리지 않도록 복사
    df = dropna(df.copy())

    # (1) 단순이동평균 (SMA)
    df["sma"] = SMAIndicator(df["close"], SMA_WIN, fillna=True).sma_indicator()

    # (2) ATR
    df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"], ATR_WIN, fillna=True).average_true_range()

    # (3) 거래량 20봉 평균
    df["vol20"] = df["volume"].rolling(20).mean()

    # (4) MACD 차이 (macd_diff)
    df["macd_diff"] = MACD(df["close"], fillna=True).macd_diff()

    return df


def calc_indicators_1h(df: pd.DataFrame) -> pd.DataFrame:
    """
    1시간봉 지표 계산:
      - SMA(50)  (예: 50시간 이동평균)
      - EMA(FAST=EMA_FAST_WINDOW, SLOW=EMA_SLOW_WINDOW)
      - RSI(RSI_WINDOW)
      - ATR(ATR_WIN)  (ATR_WIN 동일하게 사용)
    """
    df = dropna(df.copy())

    # (1) 1시간봉 SMA 50
    df["sma50_1h"] = SMAIndicator(df["close"], 50, fillna=True).sma_indicator()

    # (2) EMA 빠른 선 / EMA 느린 선
    df["ema_fast_1h"] = EMAIndicator(df["close"], window=EMA_FAST_WINDOW, fillna=True).ema_indicator()
    df["ema_slow_1h"] = EMAIndicator(df["close"], window=EMA_SLOW_WINDOW, fillna=True).ema_indicator()

    # (3) RSI
    df["rsi_1h"] = RSIIndicator(df["close"], window=RSI_WINDOW, fillna=True).rsi()

    # (4) ATR (1시간봉용 ATR, ATR_WIN 그대로 사용)
    df["atr_1h"] = AverageTrueRange(df["high"], df["low"], df["close"], ATR_WIN, fillna=True).average_true_range()

    return df
