# trading_bot/data_io.py

import json
import os
import time
import logging
import tempfile

import pandas as pd
import pyupbit
import requests

from trading_bot.config import TICKER, INTERVAL, CACHE_FILE, CACHE_TTL

logger = logging.getLogger(__name__)

# 1시간봉 캐시용 파일과 TTL
CACHE_FILE_1H = CACHE_FILE.parent / "ohlcv_cache_1h.json"
CACHE_TTL_1H  = CACHE_TTL * 4  # 예: 15분봉 TTL의 4배 (1시간 TTL)

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


def load_cached_ohlcv_1h() -> pd.DataFrame | None:
    """
    1시간봉 캐시 로딩
    - 파일이 없거나 JSON 파싱 불가 → None
    - TTL 경과 → None
    - DataFrame에 필수 컬럼(open, high, low, close, volume)이 누락되면 캐시 무효 → None
    """
    if not os.path.exists(CACHE_FILE_1H):
        return None

    try:
        with open(CACHE_FILE_1H, "r", encoding="utf-8") as f:
            raw = json.load(f)

        ts_saved = raw.get("ts", 0)
        if time.time() - ts_saved > CACHE_TTL_1H:
            return None

        ohlcv_dict = raw.get("ohlcv", {})
        df = pd.DataFrame.from_dict(ohlcv_dict, orient="index", dtype=float)
        df.index = pd.to_datetime(df.index, errors="coerce")

        # 필수 컬럼 검사
        if not REQUIRED_COLUMNS.issubset(df.columns):
            missing = REQUIRED_COLUMNS - set(df.columns)
            logger.warning(f"load_cached_ohlcv_1h: 캐시에 필수 컬럼 누락 {missing} → 캐시 무효 처리")
            try:
                os.remove(CACHE_FILE_1H)
            except Exception:
                logger.exception("load_cached_ohlcv_1h: 손상된 캐시 삭제 중 예외 발생")
            return None

        return df

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"load_cached_ohlcv_1h: 캐시 파일 손상({e}) → 삭제 후 None 반환")
        try:
            os.remove(CACHE_FILE_1H)
        except Exception:
            logger.exception("load_cached_ohlcv_1h: 캐시 파일 삭제 중 예외 발생")
        return None

    except Exception:
        logger.exception("load_cached_ohlcv_1h: 예외 발생 → None 반환")
        return None


def save_cached_ohlcv_1h(df: pd.DataFrame) -> None:
    """
    1시간봉 캐시 저장
    - orient="index"로 저장
    - 인덱스를 문자열로 변환해서 JSON 직렬화가 가능하도록 함
    - 임시 파일에 먼저 쓰고 os.replace()로 원자적 교체
    """
    try:
        os.makedirs(os.path.dirname(CACHE_FILE_1H), exist_ok=True)

        dirpath = os.path.dirname(CACHE_FILE_1H)
        with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tmpf:
            cp = df.copy()
            # 인덱스를 문자열로 변환
            cp.index = cp.index.astype(str)
            data = {"ts": time.time(), "ohlcv": cp.to_dict(orient="index")}
            json.dump(data, tmpf)
            tmp_name = tmpf.name

        os.replace(tmp_name, CACHE_FILE_1H)

    except Exception:
        logger.exception("save_cached_ohlcv_1h: 캐시 저장 중 예외 발생")
        try:
            if "tmp_name" in locals() and os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            logger.exception("save_cached_ohlcv_1h: 임시 파일 삭제 중 예외 발생")


def fetch_direct() -> pd.DataFrame | None:
    """
    Upbit REST API(15분봉)로 직접 데이터를 가져오는 백업 함수.
    """
    try:
        unit = INTERVAL.replace("minute", "")
        url = f"https://api.upbit.com/v1/candles/minutes/{unit}"
        resp = requests.get(url, params={"market": TICKER, "count": 100}, timeout=5)
        resp.raise_for_status()
        data = resp.json()[::-1]
        df = pd.DataFrame(data).rename(columns={
            "opening_price": "open",
            "high_price":    "high",
            "low_price":     "low",
            "trade_price":   "close",
            "candle_acc_trade_volume": "volume",
        })
        df.index = pd.to_datetime(df["candle_date_time_kst"], errors="coerce")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        logger.exception("fetch_direct() 실패")
        return None


def safe_ohlcv() -> pd.DataFrame | None:
    """
    pyupbit.get_ohlcv() → 실패 시 fetch_direct() 로 백업
    """
    try:
        df = pyupbit.get_ohlcv(TICKER, count=100, interval=INTERVAL)
        if df is None or df.empty:
            raise RuntimeError("pyupbit.get_ohlcv 빈 데이터")
        return df
    except Exception:
        logger.warning("pyupbit.get_ohlcv 에러 발생, fetch_direct 시도")
        return fetch_direct()


def fetch_data_15m() -> pd.DataFrame:
    """
    15분봉 OHLCV 데이터 로드 (캐시 → API 호출 → 캐시 저장)
    """
    df = load_cached_ohlcv()
    if df is None or df.empty:
        df = safe_ohlcv()
        if df is not None and not df.empty:
            save_cached_ohlcv(df)
    if df is None or df.empty:
        raise RuntimeError("OHLCV 데이터 로딩 실패 (15분봉)")
    return df


def fetch_data_1h(ticker: str, count: int = 100) -> pd.DataFrame | None:
    """
    1시간봉 OHLCV 데이터 로드 (캐시 → pyupbit.get_ohlcv → REST 백업)
    """
    df = load_cached_ohlcv_1h()
    if df is not None and not df.empty:
        return df

    try:
        df_live = pyupbit.get_ohlcv(ticker, interval="minute60", count=count)
        if df_live is None or df_live.empty:
            raise RuntimeError("pyupbit.get_ohlcv(1h) 빈 데이터")
        save_cached_ohlcv_1h(df_live)
        return df_live
    except Exception:
        logger.warning("fetch_data_1h: pyupbit.get_ohlcv 실패 → REST fetch 시도")
        try:
            df_backup = fetch_ohlcv_1h_via_rest(ticker, count)
            if df_backup is not None:
                save_cached_ohlcv_1h(df_backup)
            return df_backup
        except Exception:
            logger.exception("fetch_data_1h: REST fetch 실패")
            return None


def fetch_ohlcv_1h_via_rest(ticker: str, count: int = 100) -> pd.DataFrame | None:
    """
    Upbit REST API(1시간봉)로 직접 데이터를 가져오는 백업 함수.
    """
    try:
        url = "https://api.upbit.com/v1/candles/minutes/60"
        resp = requests.get(url, params={"market": ticker, "count": count}, timeout=5)
        resp.raise_for_status()
        data = resp.json()[::-1]
        df = pd.DataFrame(data).rename(columns={
            "opening_price": "open",
            "high_price":    "high",
            "low_price":     "low",
            "trade_price":   "close",
            "candle_acc_trade_volume": "volume",
        })
        df.index = pd.to_datetime(df["candle_date_time_kst"], errors="coerce")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        logger.exception("fetch_ohlcv_1h_via_rest() 실패")
        return None
