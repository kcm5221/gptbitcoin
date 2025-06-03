# trading_bot/strategies.py

import logging
from typing import Tuple

from ta.trend import EMAIndicator

from trading_bot.candle_patterns import is_volume_spike
from trading_bot.config import (
    VOLUME_SPIKE_THRESHOLD,
    SMA_WINDOW,
    EMA_FAST_WINDOW,
    EMA_SLOW_WINDOW,
    EMA_CROSS_BAND,
)

logger = logging.getLogger(__name__)


def apply_strategy_A(ctx) -> Tuple[bool, bool, str]:
    """
    보조 전략 A: 볼륨 스파이크 + price > SMA30 → 매수
               / BTC 보유 중 & price < SMA30 → 매도
    - ctx.sma30, ctx.volume, ctx.vol20가 None이거나 누락되면 스킵
    - VOLUME_SPIKE_THRESHOLD를 사용하여 스파이크 판정
    - 로그에 실제 값 기록
    """
    try:
        # (1) 필수 지표 유효성 검사
        if ctx.sma30 is None or ctx.volume is None or ctx.vol20 is None:
            logger.warning(
                f"apply_strategy_A: 지표 누락 (sma30={ctx.sma30}, volume={ctx.volume}, vol20={ctx.vol20}) → 스킵"
            )
            return False, False, ""

        # (2) 볼륨 스파이크 판정
        vs = is_volume_spike(ctx.volume, ctx.vol20)
        logger.debug(
            f"apply_strategy_A: volume={ctx.volume:.2f}, vol20={ctx.vol20:.2f}, "
            f"threshold={VOLUME_SPIKE_THRESHOLD}, vs={vs}"
        )
        if vs and ctx.price > ctx.sma30:
            logger.info(
                f"apply_strategy_A: 볼륨스파이크(vs=True) & price({ctx.price:.2f}) > sma30({ctx.sma30:.2f}) → 매수"
            )
            return True, False, f"volume+SMA{SMA_WINDOW}"

        # (3) BTC 보유 중 & price < SMA30 → 매도
        if ctx.btc > 0 and ctx.price < ctx.sma30:
            logger.info(
                f"apply_strategy_A: BTC 보유 중 & price({ctx.price:.2f}) < sma30({ctx.sma30:.2f}) → 매도"
            )
            return False, True, f"price<SMA{SMA_WINDOW}"

        return False, False, ""

    except Exception:
        logger.exception("apply_strategy_A: 예외 발생 → 스킵")
        return False, False, ""


def apply_strategy_B(ctx) -> Tuple[bool, bool, str]:
    """
    보조 전략 B: EMA(FAST/SLOW) 기반 골든 크로스 → 매수
               / 데드 크로스 → 매도
    - ctx.df_15m이 None이거나 길이 < (EMA_SLOW_WINDOW + 1) 이면 스킵
    - 마지막 EMA_SLOW_WINDOW+1개의 종가만 슬라이싱하여 EMA 계산
    - EMA_CROSS_BAND 이상으로 차이가 벌어질 때만 진입
    - 실제 EMA 값(이전/현재)을 로그에 기록
    """
    try:
        df = ctx.df_15m
        if df is None:
            logger.warning("apply_strategy_B: df_15m이 None → 스킵")
            return False, False, ""

        min_len = EMA_SLOW_WINDOW + 1
        if len(df) < min_len:
            logger.warning(
                f"apply_strategy_B: 데이터 부족 (len={len(df)} < {min_len}) → 스킵"
            )
            return False, False, ""

        # (1) 마지막 EMA_SLOW_WINDOW+1개의 종가만 추출
        closes = df["close"].iloc[-min_len:]

        # (2) 이전 구간(close[:-1]) EMA 계산 (증분 방식)
        prev_closes = closes.iloc[:-1]
        prev_fast = EMAIndicator(prev_closes, window=EMA_FAST_WINDOW, fillna=True).ema_indicator().iloc[-1]
        prev_slow = EMAIndicator(prev_closes, window=EMA_SLOW_WINDOW, fillna=True).ema_indicator().iloc[-1]

        # (3) 현재 구간 전체(close) EMA 계산
        ema_fast = EMAIndicator(closes, window=EMA_FAST_WINDOW, fillna=True).ema_indicator().iloc[-1]
        ema_slow = EMAIndicator(closes, window=EMA_SLOW_WINDOW, fillna=True).ema_indicator().iloc[-1]

        # (4) EMA 값과 밴드 차이 로그
        diff_prev = prev_fast - prev_slow
        diff_curr = ema_fast - ema_slow
        logger.debug(
            f"apply_strategy_B: prev_fast={prev_fast:.2f}, prev_slow={prev_slow:.2f}, "
            f"ema_fast={ema_fast:.2f}, ema_slow={ema_slow:.2f}, "
            f"diff_prev={diff_prev:.2f}, diff_curr={diff_curr:.2f}, band={EMA_CROSS_BAND}"
        )

        # (5) 골든 크로스: 이전 diff ≤ 0, 현재 diff > 0, 절대 차 > EMA_CROSS_BAND
        # (5) 골든 크로스: 이전 diff ≤ 0, 현재 diff > 0  → 밴드 조건 잠시 제거
        if diff_prev <= 0 and diff_curr > 0:
            logger.info(
                f"apply_strategy_B: [완화판] EMA 골든 크로스 → 매수 "
                f"(prev_fast={prev_fast:.2f}, prev_slow={prev_slow:.2f}, "
                f"ema_fast={ema_fast:.2f}, ema_slow={ema_slow:.2f})"
            )
            return True, False, f"EMA{EMA_FAST_WINDOW}/{EMA_SLOW_WINDOW}_GC"

        # (6) 데드 크로스: 이전 diff ≥ 0, 현재 diff < 0  → 밴드 조건 잠시 제거
        if diff_prev >= 0 and diff_curr < 0:
            logger.info(
                f"apply_strategy_B: [완화판] EMA 데드 크로스 → 매도 "
                f"(prev_fast={prev_fast:.2f}, prev_slow={prev_slow:.2f}, "
                f"ema_fast={ema_fast:.2f}, ema_slow={ema_slow:.2f})"
            )
            return False, True, f"EMA{EMA_FAST_WINDOW}/{EMA_SLOW_WINDOW}_DC"

        return False, False, ""

    except Exception:
        logger.exception("apply_strategy_B: 예외 발생 → 스킵")
        return False, False, ""
