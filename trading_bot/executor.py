# trading_bot/executor.py

import time
import os
import logging
from typing import Tuple

import pyupbit
import requests

from trading_bot.account_sync import sync_account_upbit
from trading_bot.db_helpers import log_indicator, log_trade
from trading_bot.db_helpers import get_recent_trades
from trading_bot.ai_helpers import ask_ai_reflection
from trading_bot.config import LIVE_MODE, TICKER, DISCORD_WEBHOOK

logger = logging.getLogger(__name__)


def execute_trade(ctx, buy_sig: bool, sell_sig: bool, pattern: str) -> Tuple[bool, float]:
    """
    실제 주문 실행 (시장가) + 동적 포지션 사이징 (ATR 기반 리스크 관리)
    return: (executed, pct_of_equity)
    """
    executed = False
    pct_used = 0.0

    if buy_sig and ctx.krw >= ctx.__dict__.get("MIN_ORDER_KRW", 0):
        risk_pct = 0.01
        if ctx.atr15 > 0:
            risk_amount = ctx.equity * risk_pct
            max_position = (risk_amount / ctx.atr15) * ctx.atr15
            max_position = min(max_position, ctx.equity * ctx.__dict__.get("PLAY_RATIO", 0))
            amt_krw = max(int(max_position), ctx.__dict__.get("MIN_ORDER_KRW", 0))
        else:
            amt_krw = ctx.__dict__.get("MIN_ORDER_KRW", 0)

        if amt_krw > ctx.krw:
            amt_krw = ctx.krw
        qty = amt_krw / ctx.price

        if amt_krw >= ctx.__dict__.get("MIN_ORDER_KRW", 0):
            executed = True
            if LIVE_MODE:
                upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", ""))
                upbit.buy_market_order(TICKER, amt_krw)
            else:
                ctx.krw -= amt_krw
                ctx.btc += qty
                ctx.avg_price = (
                    ctx.avg_price * (ctx.btc - qty) + amt_krw
                ) / ctx.btc if ctx.btc else ctx.price
            pct_used = amt_krw / ctx.equity * 100

    elif sell_sig and ctx.btc > 0:
        qty = ctx.btc
        value = qty * ctx.price
        if value >= ctx.__dict__.get("MIN_ORDER_KRW", 0):
            executed = True
            if LIVE_MODE:
                upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY", ""), os.getenv("UPBIT_SECRET_KEY", ""))
                upbit.sell_market_order(TICKER, qty)
            else:
                ctx.krw += value
                ctx.btc -= qty
            pct_used = 100.0

    if LIVE_MODE and executed:
        new_krw, new_btc, new_avg = sync_account_upbit()
        ctx.krw, ctx.btc, ctx.avg_price = new_krw, new_btc, new_avg

    return executed, pct_used


def log_and_notify(ctx, buy_sig: bool, sell_sig: bool, pattern: str, executed: bool, pct_used: float):
    """
    - 지표/매매 로그를 DB에 기록
    - 디스코드 알림 (실제 체결된 경우만)
    """
    ts = time.time()
    log_indicator(
        ts,
        ctx.sma30, ctx.atr15, ctx.vol20,
        ctx.macd, ctx.price, ctx.fear_idx
    )
    decision = "buy" if buy_sig else ("sell" if sell_sig else "hold")
    reason = pattern if pattern else "No signal"
    log_trade(
        ts, decision, pct_used, pattern or "", reason,
        ctx.btc, ctx.krw, ctx.avg_price, ctx.price,
        ("live" if LIVE_MODE else "virtual"),
        ask_ai_reflection(get_recent_trades(20), ctx.fear_idx) or ""
    )

    logger.info(
        "Executed=%s pct=%.2f mode=%s | Pattern=%s | Equity=%.0f | KRW=%.0f | BTC=%.6f",
        executed, pct_used, ("live" if LIVE_MODE else "virtual"),
        pattern or "none", ctx.equity, ctx.krw, ctx.btc
    )

    if DISCORD_WEBHOOK:
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
            msg = (
                f"자동매매 결과: **HOLD**\n"
                f"- 패턴: {pattern or 'none'}\n"
                f"- 현재가: {ctx.price:.0f} KRW\n"
                f"- KRW 잔고: {ctx.krw:.0f} KRW\n"
                f"- BTC 잔고: {ctx.btc:.6f} BTC\n"
                f"- 이유: {reason}\n"
            )
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
