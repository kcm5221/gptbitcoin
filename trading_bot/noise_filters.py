# trading_bot/noise_filters.py

import numpy as np
import pandas as pd

def is_rule_based_noise(last_five: pd.DataFrame) -> bool:
    """
    최근 5봉 중 마지막 봉에 대해 완화된 룰 기반 이상치 판별:
      1) 결측치(시가, 고가, 저가, 종가, 거래량 중 하나라도 NaN)
      2) 마지막 봉 거래량 ≤ 최근 4봉 평균 거래량의 1/50
      3) 가격 범위 검사 삭제 (high-low 기준 없음)
    """
    # 1) 결측치 검사
    if last_five.iloc[-1][["open", "high", "low", "close", "volume"]].isnull().any():
        return True

    last = last_five.iloc[-1]
    prev4 = last_five.iloc[:-1]

    # 2) 거래량 이상치: 마지막 봉의 volume이 최근 4봉 평균 volume의 1/50 이하일 때만 노이즈로 간주
    avg_vol4 = np.nanmean(prev4["volume"])
    if avg_vol4 and avg_vol4 > 0:
        if last["volume"] <= avg_vol4 * 0.02:  # 1/50 = 0.02
            return True

    # 3) 가격 범위 검사 삭제 (기존 버전에서 제거됨)
    return False
