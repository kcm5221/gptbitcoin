# trading_bot/ai_helpers.py

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import pandas as pd
from openai import OpenAI
import requests

from trading_bot.config import PATTERN_HISTORY_FILE

logger = logging.getLogger(__name__)

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
client     = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def ask_ai_reflection(df: pd.DataFrame, fear_idx: int) -> Optional[str]:
    """
    최근 trade_log 20건과 fear_idx를 GPT-4o 모델에 넘겨서
    120 토큰 이내 분량의 “반성 일기”를 받아옴.
    """
    if client is None:
        return None

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
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("ask_ai_reflection() 실패: %s", e)
        return None


def load_pattern_history() -> List[Dict[str, Any]]:
    """
    pattern_history.json이 존재하면 불러와서 리스트로 반환.
    없으면 빈 리스트 리턴.
    """
    try:
        if PATTERN_HISTORY_FILE.exists():
            return json.loads(PATTERN_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("load_pattern_history() 실패: %s", e)
    return []


def save_pattern_history_entry(entry: Dict[str, Any]) -> None:
    """
    새로운 패턴 발생 기록(entry: {timestamp, pattern, decision, result})을
    pattern_history.json에 append하여 저장.
    """
    history = load_pattern_history()
    history.append(entry)
    try:
        with open(PATTERN_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("save_pattern_history_entry() 실패: %s", e)


def ask_candle_patterns(df_recent: pd.DataFrame) -> Optional[List[Dict[str, Any]]]:
    """
    최근 15분봉 DataFrame(예: 100봉)을 AI에게 보내어,
    복합 차트 패턴을 자동으로 태깅한 결과를 JSON으로 반환.
    코드 블록 응답을 자동으로 제거하여 순수 JSON으로 파싱.
    """
    if client is None:
        return None

    df_for_ai = df_recent.reset_index().rename(columns={"index": "datetime"})
    records   = df_for_ai.to_dict(orient="records")
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

        # 코드 블록 제거
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                raw = parts[1].strip()
        if raw.startswith("json"):
            raw = raw[len("json"):].strip()
        raw = raw.strip()

        logger.info(f"AI 원시 응답(코드 블록 제거 후): {raw}")
        patterns = json.loads(raw)
        return patterns
    except Exception as e:
        logger.warning("ask_candle_patterns() 실패: %s", e)
        return None


def ask_noise_filter(df_last5: pd.DataFrame) -> Optional[bool]:
    """
    최근 5봉 DataFrame을 AI에게 보여주어, 현재 시점(가장 최근 봉)이 노이즈인지 정상인지 판단.
    """
    if client is None:
        return False

    records   = df_last5.to_dict(orient="records")
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
        return answer.startswith("yes")
    except Exception as e:
        logger.warning("ask_noise_filter() 실패: %s", e)
        return False


def ask_pattern_decision(pattern_name: str, recent_data: pd.DataFrame) -> str:
    """
    AI에게 “이 패턴이 지금 나타났는데, 매수(buy), 매도(sell), 관망(hold) 중 어느 쪽이 좋을지를 판단해 달라” 요청.
    pattern_name: 감지된 패턴 이름 (소문자)
    recent_data: 전체 DataFrame (캔들 정보) – AI에게 최근 10봉만 전달
    반환값: 'buy', 'sell', 또는 'hold'
    """
    if client is None:
        return "hold"

    df_for_ai = recent_data.iloc[-10:].reset_index().rename(columns={"index": "datetime"})
    records   = df_for_ai.to_dict(orient="records")
    data_json = json.dumps(records, default=str)

    # 과거 히스토리에서 해당 패턴이 얼마나 자주 등장했고, 수익/손실이 어땠는지 요약
    history = load_pattern_history()
    matched = [h for h in history if h.get("pattern") == pattern_name]
    wins   = 0
    losses = 0
    profits = []
    for h in matched:
        res = h.get("result", 0)
        try:
            val = float(res)
            profits.append(val)
            if val > 0:
                wins += 1
            else:
                losses += 1
        except:
            pass
    total = len(profits)
    if total > 0:
        win_rate   = wins / total
        avg_return = sum(profits) / total
    else:
        win_rate   = None
        avg_return = None

    if total > 0:
        history_summary = (
            f"This pattern appeared {total} times before. "
            f"Win rate: {win_rate:.1%}, avg return: {avg_return:.2f}%. "
        )
    else:
        history_summary = "This pattern has no recorded history."

    prompt = (
        f"You are an experienced crypto trading AI.\n"
        f"Pattern: '{pattern_name}' detected.\n"
        f"{history_summary}\n\n"
        f"Below are the last 10 15-minute candles (JSON with datetime, open, high, low, close, volume):\n"
        f"{data_json}\n\n"
        "Based on this pattern and recent price action plus historical performance, "
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
            return "buy"
        if "sell" in raw:
            return "sell"
        return "hold"
    except Exception as e:
        logger.warning("ask_pattern_decision() 실패: %s", e)
        return "hold"
