# trading_bot/patterns.py

import logging
import time
import pandas as pd
from typing import Tuple

from trading_bot.candle_patterns import (
    is_double_bottom,
    is_double_top,
    is_volume_spike,
    is_hammer,
    is_inverted_hammer,
    is_doji,
)
from trading_bot.ai_helpers import (
    ask_candle_patterns,
    ask_pattern_decision,
    save_pattern_history_entry,
)

from trading_bot.config import VOLUME_THRESHOLD, FG_SELL_TH

logger = logging.getLogger(__name__)

KNOWN_PATTERNS = {
    "double bottom",
    "double top",
    "hammer",
    "inverted hammer",
    "doji",
}


def check_rule_patterns(ctx) -> Tuple[bool, bool, str]:
    """
    룰 기반 패턴 검사 (이중바닥, 이중천장, 단일봉+볼륨, Stop/Loss, Take/Profit, Trend-sell)
    return: (buy_signal, sell_signal, pattern_name)
    """
    # 1) 이중바닥 / 이중천장 (최근 3봉)
    df_last3 = ctx.df_15m.iloc[-3:].copy()
    if is_double_bottom(df_last3):
        logger.info("룰: 이중바닥 패턴 → 매수")
        return True, False, "double bottom"
    if is_double_top(df_last3):
        logger.info("룰: 이중천장 패턴 → 매도")
        return False, True, "double top"

    # 2) 단일봉 패턴 + 거래량 스파이크 (Hammer/InvHammer/Doji)
    vs = is_volume_spike(ctx.volume, ctx.vol20, threshold=VOLUME_THRESHOLD)
    ham = is_hammer(ctx.last_15m)
    invh = is_inverted_hammer(ctx.last_15m)
    doj = is_doji(ctx.last_15m, tolerance=0.001)

    if vs and ham:
        logger.info("룰: Hammer + 볼륨 스파이크 → 매수")
        return True, False, "hammer"
    if vs and invh:
        logger.info("룰: Inverted Hammer + 볼륨 스파이크 → 매수")
        return True, False, "inverted hammer"
    if vs and doj:
        logger.info("룰: Doji + 볼륨 스파이크 → 매수/보류")
        return True, False, "doji"

    # 3) Stop-loss / Take-profit / Trend-sell
    if ctx.btc > 0:
        # Stop-loss
        if ctx.price <= ctx.avg_price * 0.94:
            logger.info("룰: Stop-loss 조건 충족 → 매도")
            return False, True, "stop_loss"
        # Take-profit
        fee = 0.0005
        target = ctx.avg_price * ((1 + fee) * 1.05 / (1 - fee))
        if ctx.price >= target:
            logger.info("룰: Take-profit 조건 충족 → 매도")
            return False, True, "take_profit"
        # Trend-sell (Fear & Greed 지수)
        if ctx.fear_idx >= FG_SELL_TH and ctx.macd < 0:
            logger.info("룰: Trend-sell 조건 충족 → 매도")
            return False, True, "trend_sell"

    return False, False, ""


def check_ai_patterns(ctx) -> Tuple[bool, bool, str]:
    """
    AI 복합 패턴 검사 및 매매 결정
    - 100봉 이상일 때만 호출
    return: (buy_signal, sell_signal, pattern_name)
    """
    if len(ctx.df_15m) < 100:
        return False, False, ""

    df100 = ctx.df_15m.iloc[-100:].copy()
    patterns = ask_candle_patterns(df100)
    if not patterns:
        return False, False, ""

    detected = None
    for p in patterns:
        start_ts = pd.to_datetime(p["start"]).timestamp()
        end_ts   = pd.to_datetime(p["end"]).timestamp()
        if start_ts <= ctx.ts_end <= end_ts:
            detected = p["pattern"].lower()
            break

    if not detected:
        return False, False, ""

    logger.info(f"AI 패턴 감지: {detected}")
    if detected in KNOWN_PATTERNS:
        logger.info(f"'{detected}'은 KNOWN_PATTERNS → 룰 기반 사용")
        return False, False, ""

    decision = ask_pattern_decision(detected, ctx.df_15m)
    logger.info(f"AI에게 '{detected}' 패턴 매매 결정 요청 → {decision}")

    entry = {
        "timestamp": time.time(),
        "pattern": detected,
        "decision": decision,
        "result": 0.0
    }
    save_pattern_history_entry(entry)

    if decision == "buy":
        return True, False, detected
    if decision == "sell":
        return False, True, detected
    return False, False, detected
