# trading_bot/filters.py

import logging
import pandas as pd

from trading_bot.noise_filters import is_rule_based_noise
from trading_bot.ai_helpers import ask_noise_filter

logger = logging.getLogger(__name__)

def filter_noise(df_last5: pd.DataFrame) -> bool:
    """
    - 룰 기반 이상치(노이즈) 필터링
    - 필요 시 AI 에 물어본 후 ‘노이즈’ 판단되면 True 반환
    """
    if is_rule_based_noise(df_last5):
        logger.info("룰 기반 노이즈 감지: 매매 스킵")
        return True

    last_vol = df_last5.iloc[-1]["volume"]
    prev4_vol = df_last5.iloc[:-1]["volume"]
    avg_vol4 = prev4_vol.mean() if not prev4_vol.empty else 0

    if avg_vol4 > 0 and last_vol <= avg_vol4 * 0.10:
        is_noise = ask_noise_filter(df_last5)
        if is_noise:
            logger.info("AI 기반 노이즈 감지 (거래량 극단 감소): 매매 스킵")
            return True
    else:
        logger.info("AI 노이즈 판단 대상 아님(거래량 정상 범위).")

    return False
