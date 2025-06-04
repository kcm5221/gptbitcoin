# trading_bot/executor.py

import time
import os
import logging
from typing import Tuple

import pyupbit
import requests

from trading_bot.account_sync import sync_account_upbit
from trading_bot.db_helpers import log_indicator, get_recent_trades
from trading_bot.config import LIVE_MODE, TICKER, DISCORD_WEBHOOK, PLAY_RATIO, MIN_ORDER_KRW

logger = logging.getLogger(__name__)


def execute_trade(ctx, buy_sig: bool, sell_sig: bool, pattern: str) -> Tuple[bool, float]:
    """
    실제 주문 실행 (시장가) + 동적 포지션 사이징 (ATR 기반 리스크 관리)
    return: (executed, pct_of_equity)
    """
    executed = False
    pct_used = 0.0

    try:
        # 매수
        if buy_sig and ctx.krw >= MIN_ORDER_KRW:
            risk_pct = 0.01
            if ctx.atr15 > 0:
                risk_amount = ctx.equity * risk_pct
                max_position = (risk_amount / ctx.atr15) * ctx.atr15
                max_position = min(max_position, ctx.equity * PLAY_RATIO)
                amt_krw = max(int(max_position), MIN_ORDER_KRW)
            else:
                amt_krw = MIN_ORDER_KRW

            if amt_krw > ctx.krw:
                amt_krw = ctx.krw
            qty = amt_krw / ctx.price

            if amt_krw >= MIN_ORDER_KRW:
                executed = True
                if LIVE_MODE:
                    try:
                        upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", ""))
                        upbit.buy_market_order(TICKER, amt_krw)
                    except Exception as e:
                        logger.exception(f"Upbit 매수 주문 실패: {e}")
                        executed = False  # 주문 실패 시 False 로 재설정
                else:
                    ctx.krw -= amt_krw
                    ctx.btc += qty
                    ctx.avg_price = (
                        ctx.avg_price * (ctx.btc - qty) + amt_krw
                    ) / ctx.btc if ctx.btc else ctx.price
                pct_used = amt_krw / ctx.equity * 100

        # 매도
        elif sell_sig and ctx.btc > 0:
            qty = ctx.btc
            value = qty * ctx.price
            if value >= MIN_ORDER_KRW:
                executed = True
                if LIVE_MODE:
                    try:
                        upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", ""))
                        upbit.sell_market_order(TICKER, qty)
                    except Exception as e:
                        logger.exception(f"Upbit 매도 주문 실패: {e}")
                        executed = False
                else:
                    ctx.krw += value
                    ctx.btc -= qty
                pct_used = 100.0

        # 실제 모드 주문 후 잔고 재동기화
        if LIVE_MODE and executed:
            new_krw, new_btc, new_avg = sync_account_upbit()
            ctx.krw, ctx.btc, ctx.avg_price = new_krw, new_btc, new_avg

    except Exception as e:
        logger.exception(f"execute_trade() 예외 발생: {e}")
        executed = False
        pct_used = 0.0

    return executed, pct_used


def log_and_notify(ctx, buy_sig: bool, sell_sig: bool, pattern: str, executed: bool, pct_used: float):
    """
    - 지표 로그를 DB에 기록
    - (중복 방지를 위해) 매매 로그는 main.py에서 이미 기록했으므로 여기서는 생략
    - 디스코드 알림 (실행 여부와 상관없이 전송)
    """
    ts = time.time()
    try:
        # 1) 지표 로그
        log_indicator(
            ts,
            ctx.sma30, ctx.atr15, ctx.vol20,
            ctx.macd, ctx.price, ctx.fear_idx
        )
    except Exception as e:
        logger.exception(f"log_indicator() 예외 발생: {e}")

    # ── 여기서 log_trade 호출을 제거하고, Discord 알림만 수행 ────────────────────────
    logger.info(
        "Executed=%s pct=%.2f mode=%s | Pattern=%s | Equity=%.0f | KRW=%.0f | BTC=%.6f",
        executed, pct_used, ("live" if LIVE_MODE else "virtual"),
        pattern or "none", ctx.equity, ctx.krw, ctx.btc
    )

    if not DISCORD_WEBHOOK:
        logger.info("DISCORD_WEBHOOK 미설정, 알림 생략")
        return

    try:
        if executed:
            action = "BUY" if buy_sig else "SELL"
            msg = (
                f"자동매매 결과: **{action}**\n"
                f"- 패턴: {pattern}\n"
                f"- 비중: {pct_used:.2f}%\n"
                f"- 가격: {ctx.price:.0f} KRW\n"
                f"- KRW 잔고: {ctx.krw:.0f} KRW\n"
                f"- BTC 잔고: {ctx.btc:.6f} BTC\n"
            )
        else:
            if buy_sig or sell_sig:
                status = "매매 신호 있으나 체결되지 않음"
            else:
                status = "매매 신호 없음(조건 미충족 or 보류)"
            msg = (
                f"자동매매 결과: **HOLD**\n"
                f"- 패턴: {pattern or 'none'}\n"
                f"- 현재가: {ctx.price:.0f} KRW\n"
                f"- KRW 잔고: {ctx.krw:.0f} KRW\n"
                f"- BTC 잔고: {ctx.btc:.6f} BTC\n"
                f"- 상태: {status}\n"
            )

        resp = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
        if resp.status_code in (200, 204):
            logger.info(f"Discord POST 성공: {resp.status_code}")
        else:
            logger.error(f"Discord POST 실패: 상태코드={resp.status_code}, 응답={resp.text}")

    except Exception as e:
        logger.exception(f"Discord Webhook 호출 중 예외 발생: {e}")
