#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autoTrading.py
- 인트라데이(15분봉) 워뇨띠 리스크 관리 + 거래량·캔들 패턴 + GPT-4o 반성 일기
- 한 파일에 핵심 로직만 남기고, config.py / utils.py를 가져와서 사용합니다.
"""

from __future__ import annotations
import time
import sqlite3
import argparse
import logging
import os

import pandas as pd
import pyupbit
import requests
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────
# 설정 불러오기
# ──────────────────────────────────────────────────────────────
load_dotenv()  # .env 파일에서 환경 변수 로드

from config import (
    LIVE_MODE, TICKER, DB_FILE, MIN_ORDER_KRW,
    PLAY_RATIO, RESERVE_RATIO, FG_BUY_TH, FG_SELL_TH
)
from utils import (
    init_db, load_account, save_account,
    log_indicator, log_trade, get_recent_trades,
    get_fear_and_greed,
    load_cached_ohlcv, save_cached_ohlcv,
    safe_ohlcv, calc_indicators,
    is_volume_spike, is_hammer, is_inverted_hammer, is_doji,
    sync_account_upbit, ask_ai_reflection, logger
)

# ──────────────────────────────────────────────────────────────
# argparse: 현재 인트라데이 모드만 있으므로 옵션은 최소화
# ──────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Auto trading bot (intraday only)")
parser.add_argument(
    "--mode",
    choices=["intraday"],
    default="intraday",
    help="Trading mode: 'intraday' (15분봉 인트라데이)"
)
args = parser.parse_args()

# ──────────────────────────────────────────────────────────────
# 알림 함수 (Discord Webhook)
# ──────────────────────────────────────────────────────────────
def notify_discord(content: str) -> None:
    from config import DISCORD_WEBHOOK
    if not DISCORD_WEBHOOK:
        return
    try:
        resp = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=5)
        if resp.status_code not in (200, 204):
            logger.error("Discord Webhook 응답 실패: %s", resp.text)
    except Exception as e:
        logger.error("notify_discord() 예외: %s", e)

# ──────────────────────────────────────────────────────────────
# 메인 자동매매 함수
# ──────────────────────────────────────────────────────────────
def ai_trading() -> None:
    try:
        # 1) DB 초기화 및 잔고 로드/동기화
        init_db()
        krw, btc, avg_price = sync_account_upbit() if LIVE_MODE else load_account()

        # 2) 15분봉 OHLCV 가져오기(캐시/백업)
        df = load_cached_ohlcv()
        if df is None or df.empty:
            df = safe_ohlcv()
        if df is None or df.empty:
            logger.error("OHLCV 데이터 로딩 실패 (15분봉)")
            return

        save_cached_ohlcv(df)
        df = calc_indicators(df)
        last = df.iloc[-1]
        ts_end = last.name.floor("15min")

        # 이미 처리된 캔들인지 확인
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        if conn.execute("SELECT 1 FROM indicator_log WHERE ts>=?", (ts_end.timestamp(),)).fetchone():
            logger.info("Candle %s 이미 처리됨 (15min)", ts_end)
            conn.close()
            return
        conn.close()

        # 3) 지표 및 가격 정보
        fear_idx = get_fear_and_greed() or 0
        price    = float(last["close"])
        sma30    = float(last["sma"])
        macd     = float(last["macd_diff"])
        vol20    = float(last["vol20"])
        volume   = float(last["volume"])

        logger.info(
            "DEBUG: price=%.0f, SMA30=%.0f, volume=%.0f, vol20=%.0f",
            price, sma30, volume, vol20
        )

        # 먼지 처리: 잔여 BTC 가치가 최소 주문 단위 미만이면 완전 청산
        if btc * price < MIN_ORDER_KRW:
            btc = 0.0
            avg_price = 0.0

        # 4) 거래량·캔들 패턴 기반 매수/매도 신호
        vs   = is_volume_spike(volume, vol20, threshold=2.0)
        ham  = is_hammer(last)
        invh = is_inverted_hammer(last)
        doj  = is_doji(last, tolerance=0.001)

        buy_signal = (price > sma30) and vs and (ham or invh or doj)
        stop_loss  = (btc > 0) and (price <= avg_price * 0.94)
        fee        = 0.0005
        target     = avg_price * ((1 + fee) * 1.05 / (1 - fee))  # 익절 목표가
        take_profit= (btc > 0) and (price >= target)
        trend_sell = (btc > 0) and (fear_idx >= FG_SELL_TH) and (macd < 0)
        sell_signal= stop_loss or take_profit or trend_sell

        if buy_signal:
            decision, reason = "buy", "volume spike + candle pattern"
        elif sell_signal:
            if stop_loss:
                reason = "Stop-loss −6%"
            elif take_profit:
                reason = "Take-profit +5%"
            else:
                reason = "Trend sell"  # macd & fear
            decision = "sell"
        else:
            decision, reason = "hold", "No signal"

        executed = False
        pct      = 0.0

        # 5) 워뇨띠 리스크 관리 기반 주문 실행
        if decision == "buy" and krw >= MIN_ORDER_KRW:
            # (A) 잔고가 50만원 이하: 전량 매수
            if krw <= 500_000:
                amt = krw
                pct = 100.0
            else:
                # (B) 잔고가 50만원 초과: Reserve & Play 비중
                reserve_amt = krw * RESERVE_RATIO
                available   = krw - reserve_amt
                if available < MIN_ORDER_KRW:
                    amt = 0.0
                    pct = 0.0
                else:
                    amt = available * PLAY_RATIO
                    if amt < MIN_ORDER_KRW:
                        amt = 0.0
                        pct = 0.0
                    else:
                        pct = (amt / krw) * 100.0

            if amt >= MIN_ORDER_KRW:
                executed = True
                if LIVE_MODE:
                    pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", "")).buy_market_order(TICKER, amt)
                else:
                    qty = amt / price
                    krw -= amt
                    btc += qty
                    avg_price = (avg_price * (acc_btc := btc - qty) + amt) / btc if btc else price

        # 6) 전량 청산 매도 로직
        elif decision == "sell" and btc > 0:
            qty   = btc
            value = qty * price
            if value >= MIN_ORDER_KRW:
                executed = True
                if LIVE_MODE:
                    pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", "")).sell_market_order(TICKER, qty)
                else:
                    krw += value
                    btc -= qty
                pct = 100.0

        # 7) 실계좌 동기화 (실거래일 때)
        if LIVE_MODE and executed:
            krw, btc, avg_price = sync_account_upbit()

        # 8) GPT-4o 반성 일기 (옵션)
        reflection = ask_ai_reflection(get_recent_trades(20), fear_idx) or ""

        # 9) DB 기록 및 로그
        save_account(krw, btc, avg_price)
        ts = time.time()
        log_indicator(ts, sma30, float(last["atr"]), vol20, macd, price, fear_idx)
        log_trade(ts, decision, pct, None, reason, btc, krw, avg_price, price, ("live" if LIVE_MODE else "virtual"), reflection)

        logger.info(
            "Executed=%s pct=%.2f mode=%s | Reason=%s",
            executed, pct, ("live" if LIVE_MODE else "virtual"), reason
        )

        # 10) Discord 알림
        msg = (
            f"� 자동매매 결과: **{decision.upper()}**\n"
            f"- 비중: {pct:.2f}%\n"
            f"- 가격: {price:.0f} KRW\n"
            f"- KRW 잔고: {krw:.0f} KRW\n"
            f"- BTC 잔고: {btc:.6f} BTC\n"
        )
        notify_discord(msg)

    except Exception as e:
        logger.error("ai_trading() 예외: %s", e, exc_info=True)
        notify_discord(f"❌ 자동매매 중 예외 발생: `{e}`")

# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ai_trading()
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨 (Ctrl+C)")
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        notify_discord(f"‼️ 자동매매 스크립트 장애: `{e}`")
