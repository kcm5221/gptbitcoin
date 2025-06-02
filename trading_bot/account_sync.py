# trading_bot/account_sync.py

import os
import logging
import pyupbit

logger = logging.getLogger(__name__)


def sync_account_upbit() -> tuple[float, float, float]:
    """
    Upbit 실계좌에서 잔고(krw, btc, avg_price)를 가져옴.
    인증 오류 등 발생 시 (0, 0, 0) 리턴.
    """
    try:
        upbit = pyupbit.Upbit(
            os.getenv("UPBIT_ACCESS_KEY", ""),
            os.getenv("UPBIT_SECRET_KEY", "")
        )
        bal = upbit.get_balances()
        if isinstance(bal, dict) and "error" in bal:
            raise RuntimeError(bal["error"]["message"])

        def _get_balance(cur: str, f: str = "balance") -> float:
            raw = next((b.get(f, "0") for b in bal if b["currency"] == cur), "0")
            return float(raw or 0.0)

        return _get_balance("KRW"), _get_balance("BTC"), _get_balance("BTC", "avg_buy_price")
    except Exception as e:
        logger.warning("sync_account_upbit() 실패: %s", e)
        return 0.0, 0.0, 0.0
