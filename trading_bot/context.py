# trading_bot/context.py

from dataclasses import dataclass
from typing import Optional

import pandas as pd

@dataclass
class SignalContext:
    # ─ 데이터 프레임
    df_15m: pd.DataFrame
    df_1h: Optional[pd.DataFrame]

    # ─ 최종 봉(15분 / 1시간)
    last_15m: pd.Series
    last_1h: Optional[pd.Series]

    # ─ 타임스탬프(초 단위)
    ts_end: float

    # ─ 기본 데이터(15분봉)
    price: float
    sma30: float
    atr15: float
    vol20: float
    macd: float
    volume: float

    # ─ 계좌 정보
    equity: float
    krw: float
    btc: float
    avg_price: float

    # ─ 보조 지표
    fear_idx: int
