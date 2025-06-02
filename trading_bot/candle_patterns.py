# trading_bot/candle_patterns.py

import pandas as pd

def is_volume_spike(last_volume: float, avg_volume_20: float, threshold: float = 2.0) -> bool:
    """
    최근 봉 거래량(last_volume)이 20봉 평균(avg_volume_20)의 threshold 배수 이상인지 판별.
    """
    if avg_volume_20 is None or avg_volume_20 == 0:
        return False
    return last_volume >= (avg_volume_20 * threshold)


def is_hammer(candle: pd.Series) -> bool:
    """
    망치형(Hammer) 판별:
    - 몸통(real_body) 대비 아래꼬리(lower_shadow)가 2배 이상 길고,
    - 위꼬리(upper_shadow)가 몸통의 30% 이내
    """
    open_price  = float(candle["open"])
    close_price = float(candle["close"])
    high_price  = float(candle["high"])
    low_price   = float(candle["low"])

    real_body    = abs(close_price - open_price)
    lower_shadow = min(open_price, close_price) - low_price
    upper_shadow = high_price - max(open_price, close_price)

    if real_body == 0:
        return False

    return (lower_shadow >= real_body * 2) and (upper_shadow <= real_body * 0.3)


def is_inverted_hammer(candle: pd.Series) -> bool:
    """
    역망치형(Inverted Hammer) 판별:
    - 몸통(real_body) 대비 위꼬리(upper_shadow)가 2배 이상 길고,
    - 아래꼬리(lower_shadow)가 몸통의 30% 이내
    """
    open_price  = float(candle["open"])
    close_price = float(candle["close"])
    high_price  = float(candle["high"])
    low_price   = float(candle["low"])

    real_body    = abs(close_price - open_price)
    lower_shadow = min(open_price, close_price) - low_price
    upper_shadow = high_price - max(open_price, close_price)

    if real_body == 0:
        return False

    return (upper_shadow >= real_body * 2) and (lower_shadow <= real_body * 0.3)


def is_doji(candle: pd.Series, tolerance: float = 0.001) -> bool:
    """
    도지(Doji) 판별:
    - 시가와 종가 차이가 전체 캔들 범위 대비 tolerance 이하인 경우
    """
    open_price  = float(candle["open"])
    close_price = float(candle["close"])
    high_price  = float(candle["high"])
    low_price   = float(candle["low"])

    total_range = high_price - low_price
    if total_range == 0:
        return False

    body_size = abs(close_price - open_price)
    return (body_size / total_range) <= tolerance


def is_double_bottom(df_recent: pd.DataFrame) -> bool:
    """
    최근 3봉을 보고 이중 바닥 패턴인지 판별.
    - low1 > low2 < low3
    - 봉2 종가(close2)가 저점(low2) 대비 1% 이상 반등
    """
    if len(df_recent) < 3:
        return False

    low1, close1 = float(df_recent.iloc[-3]["low"]), float(df_recent.iloc[-3]["close"])
    low2, close2 = float(df_recent.iloc[-2]["low"]), float(df_recent.iloc[-2]["close"])
    low3, close3 = float(df_recent.iloc[-1]["low"]), float(df_recent.iloc[-1]["close"])

    if not (low1 > low2 and low2 < low3):
        return False
    if close2 <= low2 * 1.01:
        return False
    return True


def is_double_top(df_recent: pd.DataFrame) -> bool:
    """
    최근 3봉을 보고 이중 천장 패턴인지 판별.
    - high1 < high2 > high3
    - 봉2 종가(close2)가 고점(high2) 대비 1% 이상 하락
    """
    if len(df_recent) < 3:
        return False

    high1, close1 = float(df_recent.iloc[-3]["high"]), float(df_recent.iloc[-3]["close"])
    high2, close2 = float(df_recent.iloc[-2]["high"]), float(df_recent.iloc[-2]["close"])
    high3, close3 = float(df_recent.iloc[-1]["high"]), float(df_recent.iloc[-1]["close"])

    if not (high1 < high2 and high2 > high3):
        return False
    if close2 >= high2 * 0.99:
        return False
    return True
