#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import time
from pathlib import Path

import pandas as pd
import requests

from trading_bot.context import SignalContext
from trading_bot.data_fetcher import fetch_data_15m, fetch_data_1h
from trading_bot.filters import filter_noise
from trading_bot.indicators_common import calc_indicators_15m
from trading_bot.indicators_1h import calc_indicators_1h
from trading_bot.patterns import check_rule_patterns, check_ai_patterns
from trading_bot.strategies import apply_strategy_A, apply_strategy_B
from trading_bot.executor import execute_trade, log_and_notify

from trading_bot.account_sync import sync_account_upbit
from trading_bot.db_helpers import (
    init_db, load_account, save_account,
    log_indicator, log_trade, log_reflection,
    has_indicator, get_recent_trades, get_last_reflection_ts
)
from trading_bot.utils import get_fear_and_greed
from trading_bot.config import (
    LIVE_MODE,
    TICKER,
    MIN_ORDER_KRW,
    VOLUME_SPIKE_THRESHOLD,
    RSI_OVERRIDE,
    MACD_1H_THRESHOLD,
    FG_EXTREME_FEAR
)
from trading_bot.env_utils import (
    read_env_vars,
    parse_suggestion,
    update_env_vars,
)

# 디버그 로그가 보이도록 레벨을 DEBUG로 설정
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


def ai_trading():
    logger.info("=== ai_trading() 시작 ===")

    # 1) DB 초기화
    init_db()
    logger.info("1) DB 초기화 완료")

    # 2) 15분봉 + 1시간봉 데이터 로드
    df_15m = fetch_data_15m()
    logger.info(f"2) 15분봉 데이터 로드 완료 (count={len(df_15m)})")
    df_1h_raw = fetch_data_1h(TICKER, count=100)
    if df_1h_raw is not None:
        df_1h = calc_indicators_1h(df_1h_raw)
        logger.info(f"   1시간봉 데이터 및 지표 계산 완료 (count={len(df_1h)})")
    else:
        df_1h = None
        logger.info("   1시간봉 데이터 없음")

    # 3) 노이즈 필터
    df_last5 = df_15m.iloc[-5:].copy()
    logger.info("3) 노이즈 필터 진입")
    if filter_noise(df_last5):
        logger.info("3) filter_noise()가 True를 반환하여 종료")
        return
    logger.info("3) 노이즈 필터 통과")

    # 4) 지표 계산 (15분봉)
    try:
        df_15m = calc_indicators_15m(df_15m)
    except Exception as e:
        logger.error("calc_indicators_15m() 예외 발생: %s", e)
        logger.error("4) 15분봉 지표 계산 실패 또는 빈 데이터 → 종료")
        return
    logger.info("4) 15분봉 지표 계산 완료")

    last_15m = df_15m.iloc[-1]
    ts_end = last_15m.name.floor("15min").timestamp()
    price = float(last_15m["close"])
    sma30 = float(last_15m["sma"])
    atr15 = float(last_15m["atr"])
    vol20 = float(last_15m["vol20"])
    macd = float(last_15m["macd_diff"])
    volume = float(last_15m["volume"])

    if df_1h is not None:
        last_1h = df_1h.iloc[-1]
    else:
        last_1h = None

    # 5) 계좌·잔고 로드
    if LIVE_MODE:
        krw, btc, avg_price = sync_account_upbit()
    else:
        krw, btc, avg_price = load_account()

    # 5-1) 공포·탐욕 지수 가져오기 (캐시 기반 최대 하루 1회)
    fear_idx = get_fear_and_greed() or 0

    equity = krw + btc * price

    ctx = SignalContext(
        df_15m=df_15m,
        df_1h=df_1h,
        last_15m=last_15m,
        last_1h=last_1h,
        ts_end=ts_end,
        price=price,
        sma30=sma30,
        atr15=atr15,
        vol20=vol20,
        macd=macd,
        volume=volume,
        equity=equity,
        krw=krw,
        btc=btc,
        avg_price=avg_price,
        fear_idx=fear_idx
    )

    # 6) 이미 처리된 봉인지 확인
    try:
        if has_indicator(ts_end):
            logger.info("Candle %s 이미 처리됨", pd.to_datetime(ts_end, unit="s"))
            return
    except Exception as e:
        logger.error("has_indicator 호출 중 예외: %s", e)
        return

    # 7) 상위 차트(1시간봉) 추세 필터 + 예외 조건(RSI, MACD, Fear)
    if ctx.df_1h is not None:
        sma50_1h = float(ctx.last_1h["sma50_1h"])
        rsi_1h   = float(ctx.last_1h["rsi_1h"])
        macd_1h  = float(ctx.last_1h["macd_diff_1h"])
        fear     = int(ctx.fear_idx)

        # ① 디버깅용 로그: 실제 지표값이 어떻게 나오는지 확인
        logger.debug(
            f"[1h 필터 직전] price={ctx.price:.0f}, sma50_1h={sma50_1h:.0f}, "
            f"rsi_1h={rsi_1h:.1f}, macd_1h={macd_1h:.1f}, fear={fear}"
        )

        if ctx.price < sma50_1h:
            # 예외 1) 1h RSI가 RSI_OVERRIDE 이하
            cond_rsi  = (rsi_1h <= RSI_OVERRIDE)
            # 예외 2) 1h MACD diff 절대값 ≤ MACD_1H_THRESHOLD
            cond_macd = (abs(macd_1h) <= MACD_1H_THRESHOLD)
            # 예외 3) Fear ≤ FG_EXTREME_FEAR
            cond_fear = (fear <= FG_EXTREME_FEAR)

            if not (cond_rsi or cond_macd or cond_fear):
                logger.info(
                    f"⏸ 거래 보류: 현재가 {ctx.price:.0f} < 1h SMA50 {sma50_1h:.0f} "
                    f"(RSI={rsi_1h:.1f}/{RSI_OVERRIDE}, |MACD1h|={abs(macd_1h):.2f}/{MACD_1H_THRESHOLD}, Fear={fear}/{FG_EXTREME_FEAR})"
                )
                log_and_notify(ctx, False, False, "sma50_filter", False, 0.0)
                return
            else:
                logger.info(
                    "1h SMA50 아래이지만 예외 조건 충족 → 진행 "
                    f"(RSI={rsi_1h:.1f}/{RSI_OVERRIDE}, |MACD1h|={abs(macd_1h):.2f}/{MACD_1H_THRESHOLD}, Fear={fear}/{FG_EXTREME_FEAR})"
                )

    # 8) 룰 기반 패턴
    df3 = ctx.df_15m.iloc[-3:][["open", "high", "low", "close", "volume"]]
    logger.debug(f"[룰패턴 직전] 최근 3봉:\n{df3.to_string(index=True)}")
    buy_sig, sell_sig, pattern = check_rule_patterns(ctx)
    logger.info(f"8) 룰 패턴 결과: buy={buy_sig}, sell={sell_sig}, pattern={pattern}")

    # 9) AI 복합 패턴 (룰 기반 신호 없을 때)
    if not (buy_sig or sell_sig):
        buy_ai, sell_ai, pat_ai = check_ai_patterns(ctx)
        if buy_ai or sell_ai:
            buy_sig, sell_sig, pattern = buy_ai, sell_ai, pat_ai
        logger.info(f"9) AI 패턴 결과: buy={buy_ai}, sell={sell_ai}, pattern={pat_ai}")

    # 10) 보조 전략 A (룰/AI 신호 없을 때)
    if not (buy_sig or sell_sig):
        buy_a, sell_a, pat_a = apply_strategy_A(ctx)
        if buy_a or sell_a:
            buy_sig, sell_sig, pattern = buy_a, sell_a, pat_a
        logger.info(f"10) 보조 전략 A 결과: buy={buy_a}, sell={sell_a}, pattern={pat_a}")

    # 11) 보조 전략 B (위에서도 신호 없을 때)
    if not (buy_sig or sell_sig):
        buy_b, sell_b, pat_b = apply_strategy_B(ctx)
        if buy_b or sell_b:
            buy_sig, sell_sig, pattern = buy_b, sell_b, pat_b
        logger.info(f"11) 보조 전략 B 결과: buy={buy_b}, sell={sell_b}, pattern={pat_b}")

    # 12) 먼지 처리: 잔여 BTC가 최소 주문액 미만일 때 시장가 매도하거나 “버림” 로그
    if ctx.btc * ctx.price < MIN_ORDER_KRW:
        if ctx.btc > 0:
            if LIVE_MODE:
                try:
                    logger.info(f"잔량 BTC({ctx.btc:.6f})가 최소 주문액 미만 → 전량 매도 시도")
                    # 실제 Upbit 시장가 매도: Upbit API 호출
                    # upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))
                    # upbit.sell_market_order(TICKER, ctx.btc)
                except Exception as e:
                    logger.exception(f"잔량 매도 시도 중 예외 발생: {e}")
            else:
                logger.info(f"잔량 BTC({ctx.btc:.6f})가 최소 주문액 미만 → 전량 버림")
        ctx.btc = 0.0
        ctx.avg_price = 0.0

    # 13) 실제 매매 실행 (리스크 관리 포함)
    executed, pct_used = execute_trade(ctx, buy_sig, sell_sig, pattern)
    logger.info(f"12) execute_trade() 결과: executed={executed}, pct={pct_used:.2f}%")

    # ── “AI 반성문”은 매매(executed=True) 시에만 생성/저장 ──────────────────────────
    reflection_id = 0
    if executed:
        try:
            last_ts = get_last_reflection_ts()
            now = time.time()
            if now - last_ts < 39600:
                logger.info("반성 생략")
            else:
                recent_trades = get_recent_trades(limit=20)
                chart_recent = ctx.df_15m.tail(100)
                env_path = Path(".env")
                env_params = read_env_vars(env_path)
                from trading_bot.ai_helpers import ask_ai_reflection
                for _ in range(3):
                    reflection_text, _ = ask_ai_reflection(
                        recent_trades,
                        ctx.fear_idx,
                        chart_recent,
                        env_params=env_params,
                        recursive=True,
                    )
                    if reflection_text:
                        reflection_id = log_reflection(time.time(), reflection_text)
                        suggestions = parse_suggestion(reflection_text)
                        if suggestions:
                            update_env_vars(suggestions, env_path)
                            env_params = read_env_vars(env_path)
                        if "더 이상 변경할 사항 없음" in reflection_text or not suggestions:
                            break
                    else:
                        break
        except Exception as e:
            logger.exception(f"반성문 생성/저장 중 예외 발생: {e}")
            reflection_id = 0
    else:
        logger.info("반성문 생성 생략: 매매가 이뤄지지 않음")

    # ── trade_log 기록 (반성문 ID 포함) ─────────────────────────────────────────────
    log_trade(
        time.time(),
        "buy" if buy_sig else ("sell" if sell_sig else "hold"),
        pct_used,
        pattern or "",
        pattern or "No signal",
        ctx.btc, ctx.krw, ctx.avg_price, ctx.price,
        ("live" if LIVE_MODE else "virtual"),
        reflection_id
    )

    # ── indicator_log에도 FNG 저장 ─────────────────────────────────────────────────
    log_indicator(
        time.time(),
        ctx.sma30, ctx.atr15, ctx.vol20,
        ctx.macd, ctx.price, ctx.fear_idx
    )

    # ── Discord 알림 호출 ───────────────────────────────────────────────────────────
    log_and_notify(ctx, buy_sig, sell_sig, pattern, executed, pct_used)

    logger.info("=== ai_trading() 종료 ===")


def main():
    parser = argparse.ArgumentParser(description="Auto trading bot (intraday only)")
    parser.add_argument(
        "--mode",
        choices=["intraday"],
        default="intraday",
        help="Trading mode: 'intraday' (15분봉 인트라데이)"
    )
    args = parser.parse_args()

    # 전체 ai_trading()을 최대 3회 재시도 루프로 감싸기
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            ai_trading()
            break
        except requests.RequestException as e:
            logger.error(f"네트워크 오류로 인해 ai_trading() 실패 (시도 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(1)
            else:
                logger.error("최대 재시도 횟수 초과, 프로그램 종료")
        except KeyboardInterrupt:
            logger.info("사용자 중단(Ctrl+C)")
            break
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)
            from trading_bot.config import DISCORD_WEBHOOK
            if LIVE_MODE and DISCORD_WEBHOOK:
                try:
                    requests.post(DISCORD_WEBHOOK, json={"content": f"자동매매 장애: `{e}`"})
                except Exception as post_err:
                    logger.exception(f"Discord 알림 중 예외 발생: {post_err}")
            break


if __name__ == "__main__":
    main()
