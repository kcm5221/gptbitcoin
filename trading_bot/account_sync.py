# trading_bot/account_sync.py

import os
import logging
import pyupbit
import requests

logger = logging.getLogger(__name__)

def sync_account_upbit() -> tuple[float, float, float]:
    """
    Upbit 실계좌에서 잔고(krw, btc, avg_price)를 가져옴.
    - 인증 오류 vs 네트워크 오류를 구분하여 로깅
    - 인증 오류 발생 시 (0.0, 0.0, 0.0) 리턴
    """
    access_key = os.getenv("UPBIT_ACCESS_KEY", "").strip()
    secret_key = os.getenv("UPBIT_SECRET_KEY", "").strip()

    if not access_key or not secret_key:
        logger.error("sync_account_upbit: Upbit API 키 또는 시크릿키가 설정되지 않음")
        return 0.0, 0.0, 0.0

    try:
        upbit = pyupbit.Upbit(access_key, secret_key)
        bal = upbit.get_balances()

        # Upbit API로부터 에러 반환 시 (인증 실패 등)
        if isinstance(bal, dict) and "error" in bal:
            err_msg = bal["error"].get("message", "알 수 없는 인증 오류")
            logger.error(f"sync_account_upbit: 인증 오류 - {err_msg}")
            return 0.0, 0.0, 0.0

        def _get_balance(cur: str, field: str = "balance") -> float:
            raw = next((b.get(field, "0") for b in bal if b.get("currency") == cur), "0")
            return float(raw or 0.0)

        krw = _get_balance("KRW")
        btc = _get_balance("BTC")
        avg_price = _get_balance("BTC", "avg_buy_price")
        return krw, btc, avg_price

    except requests.exceptions.RequestException as e:
        logger.exception(f"sync_account_upbit: 네트워크 오류 - {e}")
        return 0.0, 0.0, 0.0

    except Exception as e:
        # 기타 예상치 못한 예외
        logger.exception(f"sync_account_upbit: 알 수 없는 오류 - {e}")
        return 0.0, 0.0, 0.0
