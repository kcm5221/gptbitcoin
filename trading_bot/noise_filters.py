import logging
import pandas as pd

from trading_bot.config import NOISE_VOL_THRESHOLD, PRICE_RANGE_THRESHOLD

logger = logging.getLogger(__name__)


def is_rule_based_noise(last_five: pd.DataFrame) -> tuple[bool, float]:
    """
    최근 5봉 중 마지막 봉에 대해 룰 기반 이상치(노이즈) 판별 및 평균 거래량 반환:
      1) 입력 데이터가 5개 미만이면: (False, 0.0)
      2) 마지막 봉에 결측치가 있으면: (True, avg_vol4)
      3) 지난 4봉의 거래량 모두 결측이면: (True, 0.0)
      4) 마지막 봉 거래량 ≤ (지난 4봉 평균 거래량 × NOISE_VOL_THRESHOLD)이면: (True, avg_vol4)
      5) (high - low) > (close × PRICE_RANGE_THRESHOLD)이면: (True, avg_vol4)
      6) 그 외: (False, avg_vol4)
    반환값: (is_noise, avg_vol4)
    """
    try:
        if last_five is None or len(last_five) < 5:
            return False, 0.0

        last = last_five.iloc[-1]
        prev4 = last_five.iloc[:-1]

        # 2) 마지막 봉 결측치 검사
        if last[["open", "high", "low", "close", "volume"]].isnull().any():
            vols_full = prev4["volume"].dropna()
            avg_vol4 = vols_full.mean() if len(vols_full) > 0 else 0.0
            logger.debug("is_rule_based_noise: 마지막 봉에 결측치 있어 노이즈 처리")
            return True, avg_vol4

        # 3) 지난 4봉 거래량 결측치 검사
        vols = prev4["volume"].dropna()
        if len(vols) == 0:
            logger.debug("is_rule_based_noise: 지난 4봉 거래량 모두 결측 → 노이즈 처리")
            return True, 0.0

        avg_vol4 = vols.mean()

        # 4) 거래량 임계치 검사
        last_vol = float(last["volume"])
        if avg_vol4 > 0 and last_vol <= avg_vol4 * NOISE_VOL_THRESHOLD:
            logger.debug(
                f"is_rule_based_noise: last_vol={last_vol:.2f} ≤ "
                f"{avg_vol4:.2f}×{NOISE_VOL_THRESHOLD} → 노이즈 처리"
            )
            return True, avg_vol4

        # 5) 가격 범위 검사
        price = float(last["close"])
        diff = float(last["high"]) - float(last["low"])
        if diff > price * PRICE_RANGE_THRESHOLD:
            logger.debug(
                f"is_rule_based_noise: 범위 diff={diff:.2f} > price×"
                f"{PRICE_RANGE_THRESHOLD} → 노이즈 처리"
            )
            return True, avg_vol4

        return False, avg_vol4

    except Exception:
        logger.exception("is_rule_based_noise() 예외 발생 → 노이즈 아님 처리 (False, 0.0)")
        return False, 0.0
