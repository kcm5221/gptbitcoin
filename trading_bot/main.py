#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import sqlite3
import time

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
from trading_bot.db_helpers import init_db, load_account, save_account, log_indicator, log_trade
from trading_bot.db_helpers import get_recent_trades
from trading_bot.ai_helpers import ask_ai_reflection
from trading_bot.config import LIVE_MODE, TICKER, DB_FILE, MIN_ORDER_KRW

logging.basicConfig(
    level=logging.INFO,
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
    df_15m = calc_indicators_15m(df_15m)
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
    # 예시로 FNG 대신 빈값(0) 넣었습니다. 실제 원하시면 get_fear_and_greed() 호출로 바꾸세요.
    fear_idx = ask_ai_reflection(get_recent_trades(20), 0) or 0
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
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    if conn.execute("SELECT 1 FROM indicator_log WHERE ts>=?", (ctx.ts_end,)).fetchone():
        logger.info("Candle %s 이미 처리됨", pd.to_datetime(ctx.ts_end, unit="s"))
        conn.close()
        return
    conn.close()

    # 7) 상위 차트(1시간봉) 추세 필터
    if ctx.df_1h is not None:
        sma50_1h = float(ctx.last_1h["sma50_1h"])
        if ctx.price < sma50_1h:
            logger.info(f"1시간봉 SMA50={sma50_1h:.0f} 아래 → 거래 보류")
            return

    # 8) 룰 기반 패턴
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
        from trading_bot.strategies import apply_strategy_A
        buy_a, sell_a, pat_a = apply_strategy_A(ctx)
        if buy_a or sell_a:
            buy_sig, sell_sig, pattern = buy_a, sell_a, pat_a
        logger.info(f"10) 보조 전략 A 결과: buy={buy_a}, sell={sell_a}, pattern={pat_a}")

    # 11) 보조 전략 B (위에서도 신호 없을 때)
    if not (buy_sig or sell_sig):
        from trading_bot.strategies import apply_strategy_B
        buy_b, sell_b, pat_b = apply_strategy_B(ctx)
        if buy_b or sell_b:
            buy_sig, sell_sig, pattern = buy_b, sell_b, pat_b
        logger.info(f"11) 보조 전략 B 결과: buy={buy_b}, sell={sell_b}, pattern={pat_b}")

    # 12) 먼지 처리: 잔여 BTC가 최소 단위 미만이면 전량 청산
    if ctx.btc * ctx.price < MIN_ORDER_KRW:
        ctx.btc = 0.0
        ctx.avg_price = 0.0

    # 13) 실제 매매 실행
    executed, pct_used = execute_trade(ctx, buy_sig, sell_sig, pattern)
    logger.info(f"12) execute_trade() 결과: executed={executed}, pct={pct_used:.2f}%")

    # ── 디버그용 출력 ──
    print(f"[DEBUG] log_and_notify 호출 직전 → executed={executed}, pct_used={pct_used}, pattern={pattern}")

    # 14) DB 기록 및 디스코드 알림
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

    try:
        ai_trading()
    except KeyboardInterrupt:
        logger.info("사용자 중단(Ctrl+C)")
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        from trading_bot.config import DISCORD_WEBHOOK
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json={"content": f"자동매매 장애: `{e}`"})


if __name__ == "__main__":
    main()
