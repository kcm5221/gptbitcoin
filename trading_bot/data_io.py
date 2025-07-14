# trading_bot/data_io.py

import json
import os
import time
import logging
import tempfile

import pandas as pd
from trading_bot.config import CACHE_FILE, CACHE_TTL

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


def load_cached_ohlcv() -> pd.DataFrame | None:
    """
    15분봉 캐시 로딩
    - 파일이 없거나 JSON 파싱 불가 → None
    - TTL 경과 → None
    - DataFrame에 필수 컬럼(open, high, low, close, volume)이 누락되면 캐시 무효 → None
    - JSON → DataFrame.from_dict(orient="index") 방식으로 복원
    """
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        ts_saved = raw.get("ts", 0)
        if time.time() - ts_saved > CACHE_TTL:
            return None

        ohlcv_dict = raw.get("ohlcv", {})
        df = pd.DataFrame.from_dict(ohlcv_dict, orient="index", dtype=float)
        df.index = pd.to_datetime(df.index, errors="coerce")

        # 필수 컬럼 검사
        if not REQUIRED_COLUMNS.issubset(df.columns):
            missing = REQUIRED_COLUMNS - set(df.columns)
            logger.warning(f"load_cached_ohlcv: 캐시에 필수 컬럼 누락 {missing} → 캐시 무효 처리")
            try:
                os.remove(CACHE_FILE)
            except Exception:
                logger.exception("load_cached_ohlcv: 손상된 캐시 삭제 중 예외 발생")
            return None

        return df

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"load_cached_ohlcv: 캐시 파일 손상({e}) → 삭제 후 None 반환")
        try:
            os.remove(CACHE_FILE)
        except Exception:
            logger.exception("load_cached_ohlcv: 캐시 파일 삭제 중 예외 발생")
        return None

    except Exception:
        logger.exception("load_cached_ohlcv: 예외 발생 → None 반환")
        return None


def save_cached_ohlcv(df: pd.DataFrame) -> None:
    """
    15분봉 캐시 저장
    - orient="index"로 저장
    - 인덱스를 문자열로 변환해서 JSON 직렬화가 가능하도록 함
    - 임시 파일에 먼저 쓰고 os.replace()로 원자적 교체
    """
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

        dirpath = os.path.dirname(CACHE_FILE)
        with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tmpf:
            cp = df.copy()
            # 인덱스를 문자열로 변환
            cp.index = cp.index.astype(str)
            data = {"ts": time.time(), "ohlcv": cp.to_dict(orient="index")}
            json.dump(data, tmpf)
            tmp_name = tmpf.name

        os.replace(tmp_name, CACHE_FILE)

    except Exception:
        logger.exception("save_cached_ohlcv: 캐시 저장 중 예외 발생")
        try:
            if "tmp_name" in locals() and os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            logger.exception("save_cached_ohlcv: 임시 파일 삭제 중 예외 발생")


