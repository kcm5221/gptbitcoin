import logging
import pandas as pd

from trading_bot.noise_filters import is_rule_based_noise
from trading_bot.ai_helpers import ask_noise_filter
from trading_bot.config import AI_NOISE_VOL_THRESHOLD

logger = logging.getLogger(__name__)


def filter_noise(df_last5: pd.DataFrame) -> bool:
    """
    - df_last5: 반드시 최근 5봉(df_last5.index[-5:] 형태)이어야 함.
    - 행이 5 미만이거나 컬럼이 누락된 경우 False 반환 (노이즈가 아닌 것으로 간주).
    """
    # 1) 입력 데이터 유효성 검사
    required_cols = {"open", "high", "low", "close", "volume"}
    if df_last5 is None or df_last5.shape[0] < 5:
        logger.warning(f"filter_noise: DataFrame 행 개수 부족 ({df_last5.shape[0] if df_last5 is not None else 0} < 5) → 스킵")
        return False
    if not required_cols.issubset(df_last5.columns):
        missing = required_cols - set(df_last5.columns)
        logger.warning(f"filter_noise: 필수 컬럼 누락 {missing} → 스킵")
        return False

    # 2) 룰 기반 노이즈 검사
    try:
        is_noise, avg_vol4 = is_rule_based_noise(df_last5)
        if is_noise:
            logger.info("룰 기반 노이즈 감지: 매매 스킵")
            return True
    except Exception:
        logger.exception("filter_noise: is_rule_based_noise 호출 중 예외 발생 → 노이즈 아님 처리")

    # 3) AI 호출 전 볼륨 통계 확인
    last_vol = df_last5.iloc[-1]["volume"]
    prev4_vol = df_last5.iloc[:-1]["volume"].dropna()
    avg_vol4 = prev4_vol.mean() if not prev4_vol.empty else 0

    # 4) 거래량 급감(임계치 이하) 시 AI 호출
    if avg_vol4 > 0 and last_vol <= avg_vol4 * AI_NOISE_VOL_THRESHOLD:
        logger.debug(
            f"filter_noise: 거래량 급감 감지 (last_vol={last_vol:.2f}, avg_vol4={avg_vol4:.2f}, "
            f"threshold={AI_NOISE_VOL_THRESHOLD})"
        )
        try:
            is_noise_ai = ask_noise_filter(df_last5)
            if is_noise_ai:
                logger.info("AI 기반 노이즈 감지: 매매 스킵")
                return True
        except Exception:
            logger.exception("filter_noise: ask_noise_filter 호출 중 예외 발생 → 노이즈 아님 처리")
    else:
        logger.debug(
            f"filter_noise: AI 호출 불필요 (last_vol={last_vol:.2f}, avg_vol4={avg_vol4:.2f}, "
            f"기준 {avg_vol4 * AI_NOISE_VOL_THRESHOLD:.2f} 이상)"
        )

    return False
