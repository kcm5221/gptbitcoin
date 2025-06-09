# trading_bot/utils.py

import logging
import time
from typing import Any, Dict, Optional

import requests

from trading_bot.config import FG_CACHE_TTL

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# “Fear & Greed” 지수 캐시
# ──────────────────────────────────────────────────────────────────────────
FNG_CACHE: Dict[str, Any] = {"ts": 0, "value": None}


def get_fear_and_greed() -> Optional[int]:
    """
    alternative.me API를 통해 Fear & Greed 지수를 가져와서,
    캐시 유효기간(FG_CACHE_TTL) 동안 재사용.
    """
    if time.time() - FNG_CACHE["ts"] < FG_CACHE_TTL and FNG_CACHE["value"] is not None:
        return FNG_CACHE["value"]

    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return FNG_CACHE["value"]
        val_str = data[0].get("value")
        if val_str is None:
            return FNG_CACHE["value"]
        val = int(val_str)
        FNG_CACHE.update(ts=time.time(), value=val)
        return val
    except Exception as e:
        logger.warning("get_fear_and_greed() 실패: %s", e)
        return FNG_CACHE["value"]


