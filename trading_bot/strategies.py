# trading_bot/strategies.py

import logging
from typing import Tuple
from ta.trend import EMAIndicator

from trading_bot.candle_patterns import is_volume_spike
from trading_bot.config import VOLUME_THRESHOLD

logger = logging.getLogger(__name__)


def apply_strategy_A(ctx) -> Tuple[bool, bool, str]:
    """
    보조 전략 A: 볼륨 스파이크 + price > SMA30 → 매수
      / BTC 보유 중 & price < SMA30 → 매도
    """
    vs = is_volume_spike(ctx.volume, ctx.vol20, threshold=VOLUME_THRESHOLD)
    if vs and ctx.price > ctx.sma30:
        logger.info("보조 전략 A: 볼륨 스파이크 + price > SMA30 → 매수")
        return True, False, "volume+SMA"
    if ctx.btc > 0 and ctx.price < ctx.sma30:
        logger.info("보조 전략 A: BTC 보유 중 & price < SMA30 → 매도")
        return False, True, "price<SMA30"
    return False, False, ""


def apply_strategy_B(ctx) -> Tuple[bool, bool, str]:
    """
    보조 전략 B: EMA(12/26) 크로스오버 (15분봉)
      - 골든 크로스 → 매수, 데드 크로스 → 매도
    """
    df = ctx.df_15m.copy()
    df["ema_fast"] = EMAIndicator(df["close"], window=12, fillna=True).ema_indicator()
    df["ema_slow"] = EMAIndicator(df["close"], window=26, fillna=True).ema_indicator()

    ema_fast = df["ema_fast"].iloc[-1]
    ema_slow = df["ema_slow"].iloc[-1]
    prev_fast = df["ema_fast"].iloc[-2]
    prev_slow = df["ema_slow"].iloc[-2]

    if prev_fast <= prev_slow and ema_fast > ema_slow:
        logger.info("보조 전략 B: EMA 골든 크로스 → 매수")
        return True, False, "EMA 12/26 golden cross"
    if prev_fast >= prev_slow and ema_fast < ema_slow:
        logger.info("보조 전략 B: EMA 데드 크로스 → 매도")
        return False, True, "EMA 12/26 death cross"
    return False, False, ""
