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
    load_pattern_history,
)
from trading_bot.config import (
    VOLUME_SPIKE_THRESHOLD,
    DOJI_TOLERANCE,
    FG_SELL_TH,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TRADING_FEE,
)

logger = logging.getLogger(__name__)

# KNOWN_PATTERNS의 키워드를 부분 문자열 매칭 방식으로 검사
KNOWN_PATTERNS = {
    "double bottom",
    "double top",
    "hammer",
    "inverted hammer",
    "doji",
}


def check_rule_patterns(ctx) -> Tuple[bool, bool, str]:
    """
    룰 기반 패턴 검사
    - ctx.df_15m이 None이거나 길이 < 3이면 안전하게 스킵
    - 필요한 컬럼(open, high, low, close, volume, sma, atr, vol20, macd_diff) 검사
    반환값: (buy_signal, sell_signal, pattern_name)
    """
    df = ctx.df_15m

    # 1) 입력 데이터 유효성 검사 (None 또는 길이 부족)
    if df is None or len(df) < 3:
        logger.warning(f"check_rule_patterns: 15분봉 데이터 부족 ({len(df) if df is not None else 0} < 3) → 스킵")
        return False, False, ""

    # 2) 필수 컬럼 검사
    required_cols = {"open", "high", "low", "close", "volume", "sma", "atr", "vol20", "macd_diff"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        logger.warning(f"check_rule_patterns: 필수 컬럼 누락 {missing} → 스킵")
        return False, False, ""

    try:
        # 3) 이중바닥 / 이중천장 (최근 3봉)
        df_last3 = df.iloc[-3:].copy()
        if is_double_bottom(df_last3):
            logger.info("룰: 이중바닥 패턴 → 매수")
            return True, False, "double bottom"
        if is_double_top(df_last3):
            logger.info("룰: 이중천장 패턴 → 매도")
            return False, True, "double top"

        # 4) 단일봉 패턴 + 볼륨 스파이크
        last_candle = df.iloc[-1]
        vs = is_volume_spike(ctx.volume, ctx.vol20)  # threshold는 함수 내부에서 config로 사용
        ham = is_hammer(last_candle)
        invh = is_inverted_hammer(last_candle)
        doj = is_doji(last_candle)

        if vs and ham:
            logger.info(f"룰: Hammer + 볼륨스파이크(th={VOLUME_SPIKE_THRESHOLD}) → 매수")
            return True, False, "hammer"
        if vs and invh:
            logger.info(f"룰: Inverted Hammer + 볼륨스파이크(th={VOLUME_SPIKE_THRESHOLD}) → 매수")
            return True, False, "inverted hammer"
        if vs and doj:
            logger.info(f"룰: Doji + 볼륨스파이크(th={VOLUME_SPIKE_THRESHOLD}) → 매수/보류")
            return True, False, "doji"

        # 5) Stop-loss / Take-profit / Trend-sell
        if ctx.btc > 0:
            # Stop-loss
            if ctx.price <= ctx.avg_price * (1 - STOP_LOSS_PCT):
                logger.info(f"룰: Stop-loss (가격 {ctx.price:.2f} ≤ avg_price×(1-{STOP_LOSS_PCT})) → 매도")
                return False, True, "stop_loss"

            # Take-profit (수수료 반영 후 순타겟)
            gross_target = ctx.avg_price * (1 + TAKE_PROFIT_PCT)
            net_target = gross_target / (1 - TRADING_FEE)
            if ctx.price >= net_target:
                logger.info(f"룰: Take-profit (가격 {ctx.price:.2f} ≥ 순타겟 {net_target:.2f}) → 매도")
                return False, True, "take_profit"

            # Trend-sell (공포·탐욕 지수 + MACD 음수)
            if ctx.fear_idx >= FG_SELL_TH and ctx.macd < 0:
                logger.info(f"룰: Trend-sell (FNG={ctx.fear_idx} ≥ {FG_SELL_TH} & MACD={ctx.macd:.2f} < 0) → 매도")
                return False, True, "trend_sell"

    except Exception:
        logger.exception("check_rule_patterns() 예외 발생 → 패턴 스킵")
        return False, False, ""

    return False, False, ""


def check_ai_patterns(ctx) -> Tuple[bool, bool, str]:
    """
    AI 복합 패턴 검사
    - ctx.df_15m이 None이거나 길이 < 100이면 안전하게 스킵
    반환값: (buy_signal, sell_signal, pattern_name)
    """
    df = ctx.df_15m

    # 1) 입력 데이터 유효성 검사 (None 또는 길이 부족)
    if df is None or len(df) < 100:
        logger.warning(f"check_ai_patterns: 15분봉 데이터 부족 ({len(df) if df is not None else 0} < 100) → 스킵")
        return False, False, ""

    df100 = df.iloc[-100:].copy()

    # 2) AI에게 패턴 호출
    try:
        patterns = ask_candle_patterns(df100)
    except Exception:
        logger.exception("check_ai_patterns: ask_candle_patterns 호출 중 예외 발생 → 패턴 스킵")
        return False, False, ""

    if not patterns:
        return False, False, ""

    # 3) 현재 ts_end 시간대에 해당하는 패턴이 있는지 검색
    detected = None
    for p in patterns:
        start_ts = pd.to_datetime(p.get("start", ""), errors="coerce").timestamp()
        end_ts   = pd.to_datetime(p.get("end", ""), errors="coerce").timestamp()
        if start_ts <= ctx.ts_end <= end_ts:
            detected = p.get("pattern", "").lower()
            break

    if not detected:
        return False, False, ""

    logger.info(f"check_ai_patterns: AI 패턴 감지 → '{detected}'")

    # 4) KNOWN_PATTERNS 부분 문자열 포함 검사 (예: "double bottom pattern"도 인식)
    if any(keyword in detected for keyword in KNOWN_PATTERNS):
        logger.info(f"'{detected}'은 KNOWN_PATTERNS에 해당 → 룰 기반 처리 우선")
        return False, False, ""

    # 5) 과거 히스토리 요약 및 로그에 남기기
    history = load_pattern_history()
    matched = [h for h in history if h.get("pattern", "").lower() in detected]
    wins = 0
    losses = 0
    profits = []
    for h in matched:
        try:
            val = float(h.get("result", 0.0))
            profits.append(val)
            if val > 0:
                wins += 1
            else:
                losses += 1
        except Exception:
            continue

    total = len(profits)
    if total > 0:
        win_rate = wins / total
        avg_return = sum(profits) / total
        logger.info(
            f"check_ai_patterns: '{detected}' 과거 히스토리 → win_rate={win_rate:.1%}, avg_return={avg_return:.2f}%"
        )
    else:
        logger.info(f"check_ai_patterns: '{detected}' 과거 히스토리 없음")

    # 6) AI에게 매매 결정 요청
    df10 = df.iloc[-10:][["open", "high", "low", "close", "volume"]]
    logger.debug(
        f"check_ai_patterns: ask_pattern_decision 직전 최근 10봉:\n{df10.to_string(index=True)}"
    )
    try:
        decision = ask_pattern_decision(detected, df)
    except Exception:
        logger.exception("check_ai_patterns: ask_pattern_decision 호출 중 예외 발생 → 관망 처리")
        return False, False, detected

    logger.debug(f"check_ai_patterns: ask_pattern_decision 직후 결정='{decision}'")

    logger.info(f"check_ai_patterns: AI 매매 결정 → {decision}")

    # 7) 패턴 히스토리 저장 (result 필드는 매매 체결 후 업데이트 예정)
    entry = {
        "timestamp": time.time(),
        "pattern": detected,
        "decision": decision,
        "result": 0.0  # executor에서 실제 체결 후 이 값이 업데이트되어야 함
    }
    save_pattern_history_entry(entry)

    # 8) 최종 반환
    if decision == "buy":
        return True, False, detected
    if decision == "sell":
        return False, True, detected
    return False, False, detected
