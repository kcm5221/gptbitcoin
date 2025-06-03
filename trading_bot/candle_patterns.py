import pandas as pd
import logging

from trading_bot.config import (
    VOLUME_SPIKE_THRESHOLD,
    DOJI_TOLERANCE,
    DOUBLE_BOTTOM_REBOUND_PCT,
    DOUBLE_TOP_DROP_PCT,
    DOUBLE_PATTERN_LOOKBACK,
)

logger = logging.getLogger(__name__)


def is_volume_spike(last_volume: float, avg_volume_20: float) -> bool:
    """
    마지막 봉 거래량(last_volume)이, 20봉 평균 거래량(avg_volume_20) × VOLUME_SPIKE_THRESHOLD 이상이면 True.
    """
    if avg_volume_20 is None or avg_volume_20 == 0:
        return False
    try:
        return last_volume >= (avg_volume_20 * VOLUME_SPIKE_THRESHOLD)
    except Exception:
        logger.exception("is_volume_spike: 계산 중 예외 발생")
        return False


def is_doji(candle: pd.Series) -> bool:
    """
    도지 검출: 실체 크기(body_size)가 전체 범위(total_range) 대비 DOJI_TOLERANCE 이하인지 판정.
    """
    if candle.isnull().any():
        return False

    try:
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])

        total_range = high_price - low_price
        if total_range == 0:
            return False

        body_size = abs(close_price - open_price)
        return (body_size / total_range) <= DOJI_TOLERANCE
    except Exception:
        logger.exception("is_doji: 계산 중 예외 발생")
        return False


def is_hammer(candle: pd.Series) -> bool:
    """
    망치형 캔들 검출: 도지 제외, 하단 그림자(lower_shadow)가 실체(real_body) × 2 이상이고,
    상단 그림자(upper_shadow)는 실체 × 0.3 이하일 때 True.
    """
    if candle.isnull().any():
        return False
    if is_doji(candle):
        return False

    try:
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])

        real_body = abs(close_price - open_price)
        if real_body == 0:
            return False

        lower_shadow = min(open_price, close_price) - low_price
        upper_shadow = high_price - max(open_price, close_price)

        return (lower_shadow >= real_body * 2) and (upper_shadow <= real_body * 0.3)
    except Exception:
        logger.exception("is_hammer: 계산 중 예외 발생")
        return False


def is_inverted_hammer(candle: pd.Series) -> bool:
    """
    역망치형 검출: 도지 제외, 상단 그림자(upper_shadow)가 실체(real_body) × 2 이상이고,
    하단 그림자(lower_shadow)는 실체 × 0.3 이하일 때 True.
    """
    if candle.isnull().any():
        return False
    if is_doji(candle):
        return False

    try:
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])

        real_body = abs(close_price - open_price)
        if real_body == 0:
            return False

        lower_shadow = min(open_price, close_price) - low_price
        upper_shadow = high_price - max(open_price, close_price)

        return (upper_shadow >= real_body * 2) and (lower_shadow <= real_body * 0.3)
    except Exception:
        logger.exception("is_inverted_hammer: 계산 중 예외 발생")
        return False


def is_double_bottom(df_recent: pd.DataFrame) -> bool:
    """
    이중바닥 검출: 마지막 DOUBLE_PATTERN_LOOKBACK 봉 중
    ‘저점–상승–저점’ 형태가 성립하고, 중간 봉 종가가 저점 대비 DOUBLE_BOTTOM_REBOUND_PCT 만큼 반등했을 때 True.
    """
    lookback = DOUBLE_PATTERN_LOOKBACK
    if df_recent is None or df_recent.shape[0] < lookback:
        return False

    try:
        sub = df_recent.iloc[-lookback:].reset_index(drop=True)
        for i in range(0, lookback - 2):
            low1 = float(sub.loc[i, "low"])
            low2 = float(sub.loc[i + 1, "low"])
            low3 = float(sub.loc[i + 2, "low"])
            close2 = float(sub.loc[i + 1, "close"])

            # “저점–상승–저점” 형태
            if not (low1 > low2 < low3):
                continue
            # “중간 봉 종가가 저점 대비 일정 비율만큼 반등”
            if close2 < low2 * (1 + DOUBLE_BOTTOM_REBOUND_PCT):
                continue
            return True
        return False
    except Exception:
        logger.exception("is_double_bottom: 계산 중 예외 발생")
        return False


def is_double_top(df_recent: pd.DataFrame) -> bool:
    """
    이중천장 검출: 마지막 DOUBLE_PATTERN_LOOKBACK 봉 중
    ‘고점–하락–고점’ 형태가 성립하고, 중간 봉 종가가 고점 대비 DOUBLE_TOP_DROP_PCT 만큼 하락했을 때 True.
    """
    lookback = DOUBLE_PATTERN_LOOKBACK
    if df_recent is None or df_recent.shape[0] < lookback:
        return False

    try:
        sub = df_recent.iloc[-lookback:].reset_index(drop=True)
        for i in range(0, lookback - 2):
            high1 = float(sub.loc[i, "high"])
            high2 = float(sub.loc[i + 1, "high"])
            high3 = float(sub.loc[i + 2, "high"])
            close2 = float(sub.loc[i + 1, "close"])

            # “고점–하락–고점” 형태
            if not (high1 < high2 > high3):
                continue
            # “중간 봉 종가가 고점 대비 일정 비율만큼 하락”
            if close2 > high2 * (1 - DOUBLE_TOP_DROP_PCT):
                continue
            return True
        return False
    except Exception:
        logger.exception("is_double_top: 계산 중 예외 발생")
        return False
