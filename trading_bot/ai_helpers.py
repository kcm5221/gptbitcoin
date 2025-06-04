# trading_bot/ai_helpers.py

import json
import logging
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from openai import OpenAI
import requests
import fcntl

from trading_bot.config import PATTERN_HISTORY_FILE

logger = logging.getLogger(__name__)
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


# ──────────────────────────────────────────────
# 간단한 메모리 기반 TTL 캐시 구현
# ──────────────────────────────────────────────

class TTLCache:
    def __init__(self, ttl_sec: float):
        self.ttl = ttl_sec
        self.store: Dict[Any, Tuple[float, Any]] = {}

    def get(self, key: Any) -> Any:
        entry = self.store.get(key)
        now = time.time()
        if entry and now - entry[0] < self.ttl:
            return entry[1]
        if entry:
            del self.store[key]
        return None

    def set(self, key: Any, value: Any) -> None:
        self.store[key] = (time.time(), value)


# (1) ask_candle_patterns 캐시: 동일 데이터(마지막 100봉)를 60초간 재사용
_candle_patterns_cache = TTLCache(ttl_sec=60.0)
# (2) ask_pattern_decision 캐시: 동일 패턴 이름 + 최근 10봉 해시를 300초(5분)간 재사용
_pattern_decision_cache = TTLCache(ttl_sec=300.0)
# (3) ask_noise_filter 캐시: 동일 5봉 데이터 해시를 30초간 재사용
_noise_filter_cache = TTLCache(ttl_sec=30.0)
# (4) ask_ai_reflection 캐시: 같은 최근 20개 트레이드 + fear_idx 조합을 86400초(1일)간 재사용
_reflection_cache = TTLCache(ttl_sec=86400.0)


def _df_hashable_key(df: pd.DataFrame, rows: int = 10) -> str:
    """
    DataFrame의 마지막 rows개 행을 JSON 문자열로 직렬화해 캐시 키로 사용
    """
    subset = df.iloc[-rows:].astype(str)
    return subset.to_json(orient="records")


def ask_ai_reflection(df: pd.DataFrame, fear_idx: int) -> Optional[str]:
    """
    최근 trade_log 20건과 fear_idx를 GPT-4o 모델에 넘겨서
    120 토큰 이내 분량의 “반성 일기”를 받아옴.
    → 캐시: 동일 df+fear_idx 조합은 1일간 캐시된 결과 재사용
    """
    if client is None:
        return None

    key = ("reflection", df.to_json(orient="records"), fear_idx)
    cached = _reflection_cache.get(key)
    if cached is not None:
        return cached

    prompt = (
        "You are a crypto trading coach.\n"
        f"Recent trades: {df.to_json(orient='records')}\n"
        f"Fear-Greed index={fear_idx}\n"
        "Respond in ≤120 words: what worked, what didn't, one improvement."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
        )
        content = resp.choices[0].message.content.strip()
        _reflection_cache.set(key, content)
        return content
    except Exception:
        logger.exception("ask_ai_reflection() 호출 중 예외 발생")
        return None


def load_pattern_history() -> List[Dict[str, Any]]:
    """
    pattern_history.json이 존재하면 불러와서 리스트로 반환.
    - 파일이 없으면 빈 리스트 반환
    - JSON 파싱 오류 시 원본을 .bak로 백업 후 빈 리스트 반환
    """
    try:
        if not PATTERN_HISTORY_FILE.exists():
            return []

        text = PATTERN_HISTORY_FILE.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, list):
            return data
        else:
            logger.warning("load_pattern_history: 파일 내용이 리스트가 아님 → 빈 리스트 반환")
            return []
    except json.JSONDecodeError as e:
        logger.warning(f"load_pattern_history: JSON 디코드 오류({e}) → 파일 백업 후 빈 리스트 반환")
        try:
            bak_path = str(PATTERN_HISTORY_FILE) + ".bak"
            os.replace(PATTERN_HISTORY_FILE, bak_path)
            logger.info(f"load_pattern_history: 손상된 파일을 백업함 → {bak_path}")
        except Exception:
            logger.exception("load_pattern_history: 파일 백업 중 예외 발생")
        return []
    except Exception:
        logger.exception("load_pattern_history() 호출 중 예외 발생 → 빈 리스트 반환")
        return []


def save_pattern_history_entry(entry: Dict[str, Any]) -> None:
    """
    새로운 패턴 발생 기록(entry: {timestamp, pattern, decision, result})을
    pattern_history.json에 append하여 저장.
    - 임시 파일에 기록 후 os.replace()로 원본 덮어쓰기 + 파일 잠금 적용
    """
    try:
        os.makedirs(os.path.dirname(PATTERN_HISTORY_FILE), exist_ok=True)
        history = load_pattern_history()
        history.append(entry)

        dirpath = os.path.dirname(PATTERN_HISTORY_FILE)
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tmpf:
            json.dump(history, tmpf, ensure_ascii=False, indent=2)
            tmp_name = tmpf.name

        # 원자적 교체, 잠금
        with open(tmp_name, "r+", encoding="utf-8") as f_tmp:
            try:
                fcntl.flock(f_tmp, fcntl.LOCK_EX)
            except IOError:
                logger.warning("save_pattern_history_entry: 임시 파일 잠금 실패")

        # 기존 파일 잠금 및 교체
        with open(PATTERN_HISTORY_FILE, "a+b") as f_orig:
            try:
                fcntl.flock(f_orig, fcntl.LOCK_EX)
            except IOError:
                logger.warning("save_pattern_history_entry: 원본 파일 잠금 실패")
            os.replace(tmp_name, PATTERN_HISTORY_FILE)

    except Exception:
        logger.exception("save_pattern_history_entry() 호출 중 예외 발생")
        try:
            if "tmp_name" in locals() and os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            pass


def ask_candle_patterns(df_recent: pd.DataFrame) -> Optional[List[Dict[str, Any]]]:
    """
    최근 15분봉 DataFrame(예: 100봉)을 AI에게 보내어,
    복합 차트 패턴을 자동으로 태깅한 결과를 JSON으로 반환.
    - 최소 100봉 이상일 때만 호출
    - 60초 TTL 캐시 적용
    - 코드 블록 제거는 정규표현식으로 처리
    """
    if client is None:
        return None

    if df_recent.shape[0] < 100:
        return None

    key = ("candle_patterns", _df_hashable_key(df_recent))
    cached = _candle_patterns_cache.get(key)
    if cached is not None:
        return cached

    df_for_ai = df_recent.reset_index().rename(columns={"index": "datetime"})
    records = df_for_ai.to_dict(orient="records")
    data_json = json.dumps(records, default=str)

    prompt = (
        "You are a chart pattern recognition assistant.\n"
        "Below is JSON for the most recent 100 15-minute candles. "
        "Each object has keys: 'datetime','open','high','low','close','volume'.\n\n"
        f"{data_json}\n\n"
        "Return ONLY a JSON array. DO NOT wrap it in markdown code fences (```).\n"
        "Do not return any extra text or explanation.\n"
        "Each element of the array (if any) must be an object with keys: "
        "'pattern','start','end'.\n"
        "If no patterns are found, return [] (just the two characters)."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        raw = resp.choices[0].message.content.strip()

        # 정규표현식으로 코드 블록 제거
        # ```json ... ``` 또는 ``` ... ```
        raw = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", raw).strip()

        try:
            patterns = json.loads(raw)
            _candle_patterns_cache.set(key, patterns)
            return patterns
        except Exception:
            logger.exception(f"ask_candle_patterns: JSON 파싱 오류, 원본 응답: {raw}")
            return None

    except Exception:
        logger.exception("ask_candle_patterns() 호출 중 예외 발생")
        return None


def ask_noise_filter(df_last5: pd.DataFrame) -> Optional[bool]:
    """
    최근 5봉 DataFrame을 AI에게 보여주어, 마지막 봉이 노이즈인지 판단.
    - 볼륨 감소가 (평균볼륨 × 0.10 이하)일 때만 AI 호출
    - 30초 TTL 캐시 적용
    """
    if client is None:
        return False

    key = ("noise_filter", _df_hashable_key(df_last5))
    cached = _noise_filter_cache.get(key)
    if cached is not None:
        return cached

    records = df_last5.to_dict(orient="records")
    data_json = json.dumps(records, default=str)

    prompt = (
        "You are a data quality assistant specialized in cryptocurrency 15-minute candle data.\n"
        "Below are 5 consecutive 15-minute candles (JSON with datetime, open, high, low, close, volume):\n\n"
        f"{data_json}\n\n"
        "We want to detect only **clear** data glitches or API errors.\n"
        "If you are absolutely certain that the most recent candle is a glitch or data error, answer strictly with 'yes'.\n"
        "If there is **any chance** that it might be a genuine price movement, answer 'no'.\n"
        "Do NOT guess. Answer only 'yes' or 'no'."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10
        )
        answer = resp.choices[0].message.content.strip().lower()
        is_noise = answer.startswith("yes")
        _noise_filter_cache.set(key, is_noise)
        return is_noise
    except Exception:
        logger.exception("ask_noise_filter() 호출 중 예외 발생")
        return False


def ask_pattern_decision(pattern_name: str, recent_data: pd.DataFrame) -> str:
    """
    AI에게 “이 패턴이 지금 나타났는데, 매수(buy), 매도(sell), 관망(hold) 중 어느 쪽이 좋을지를 판단해 달라” 요청.
    - 패턴 이름 + 최근 10봉 상황이 동일하면 5분간 캐시된 결정 재사용
    - 패턴 히스토리가 빈 상태일 때 유연한 힌트 제공
    """
    if client is None:
        return "hold"

    key = ("pattern_decision", pattern_name, _df_hashable_key(recent_data, rows=10))
    cached = _pattern_decision_cache.get(key)
    if cached is not None:
        return cached

    df_for_ai = recent_data.iloc[-10:].reset_index().rename(columns={"index": "datetime"})
    records = df_for_ai.to_dict(orient="records")
    data_json = json.dumps(records, default=str)

    history = load_pattern_history()
    matched = [h for h in history if h.get("pattern") == pattern_name]
    wins = 0
    losses = 0
    profits: List[float] = []
    for h in matched:
        try:
            val = float(h.get("result", 0))
            profits.append(val)
            if val > 0:
                wins += 1
            else:
                losses += 1
        except Exception:
            pass

    total = len(profits)
    if total > 0:
        win_rate = wins / total
        avg_return = sum(profits) / total
        history_summary = (
            f"This pattern appeared {total} times before. "
            f"Win rate: {win_rate:.1%}, avg return: {avg_return:.2f}%. "
        )
    else:
        history_summary = (
            "No recorded history for this pattern. Proceed with caution. "
        )

    prompt = (
        f"You are an experienced crypto trading AI.\n"
        f"Pattern: '{pattern_name}' detected.\n"
        f"{history_summary}\n\n"
        f"Below are the last 10 15-minute candles (JSON with datetime, open, high, low, close, volume):\n"
        f"{data_json}\n\n"
        "Based on this pattern and recent price action plus historical performance (if any), "
        "what should we do? Answer strictly with one of: 'buy', 'sell', or 'hold'.\n"
        "Explain reasoning in one sentence, then return only the keyword."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30
        )
        raw = resp.choices[0].message.content.strip().lower()
        if "buy" in raw:
            decision = "buy"
        elif "sell" in raw:
            decision = "sell"
        else:
            decision = "hold"
        _pattern_decision_cache.set(key, decision)
        return decision
    except Exception:
        logger.exception("ask_pattern_decision() 호출 중 예외 발생")
        return "hold"


def ask_ai_parameter_tuning() -> str:
    """최근 100개 15분봉 데이터와 현재 주요 파라미터를 GPT에 보내어
    파라미터 조정 제안을 문자열로 받아온다."""
    if client is None:
        return ""

    from trading_bot.data_fetcher import fetch_data_15m
    from trading_bot.config import (
        SMA_WINDOW,
        ATR_WINDOW,
        VOLUME_SPIKE_THRESHOLD,
        RSI_OVERRIDE,
        MACD_1H_THRESHOLD,
        FG_EXTREME_FEAR,
    )

    df = fetch_data_15m()
    if df is None or df.empty:
        return ""

    df_recent = df.tail(100).reset_index().rename(columns={"index": "datetime"})
    candles_json = json.dumps(df_recent.to_dict(orient="records"), default=str)

    prompt = (
        "You are a crypto trading strategy optimizer.\n"
        "Below is JSON for the most recent 100 15-minute candles.\n"
        f"{candles_json}\n\n"
        "Current parameters:\n"
        f"SMA_WINDOW={SMA_WINDOW}\n"
        f"ATR_WINDOW={ATR_WINDOW}\n"
        f"VOLUME_SPIKE_THRESHOLD={VOLUME_SPIKE_THRESHOLD}\n"
        f"RSI_OVERRIDE={RSI_OVERRIDE}\n"
        f"MACD_1H_THRESHOLD={MACD_1H_THRESHOLD}\n"
        f"FG_EXTREME_FEAR={FG_EXTREME_FEAR}\n\n"
        "Suggest new parameter values in the format 'KEY=VALUE'. "
        "If no changes are needed, answer '더 이상 변경할 사항 없음'.\n"
        "Return only the suggestion string."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("ask_ai_parameter_tuning() 호출 중 예외 발생")
        return ""
