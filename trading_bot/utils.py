# trading_bot/utils.py

import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional

import requests

from trading_bot.config import FG_CACHE_TTL, FNG_CACHE_FILE

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# “Fear & Greed” 지수 캐시
# ──────────────────────────────────────────────────────────────────────────
FNG_CACHE: Dict[str, Any] = {"ts": 0, "value": None}


def _load_fng_cache() -> None:
    """Load FNG cache from disk if available."""
    if not FNG_CACHE_FILE.exists():
        return
    try:
        with open(FNG_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            FNG_CACHE.update(ts=data.get("ts", 0), value=data.get("value"))
    except Exception:
        logger.warning("_load_fng_cache 실패")


def _save_fng_cache() -> None:
    """Persist FNG cache to disk."""
    try:
        os.makedirs(FNG_CACHE_FILE.parent, exist_ok=True)
        dirpath = FNG_CACHE_FILE.parent
        with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tmpf:
            json.dump(FNG_CACHE, tmpf)
            tmp_name = tmpf.name
        os.replace(tmp_name, FNG_CACHE_FILE)
    except Exception:
        logger.warning("_save_fng_cache 실패")


_load_fng_cache()


def get_fear_and_greed() -> Optional[int]:
    """
    alternative.me API를 통해 Fear & Greed 지수를 가져와서,
    캐시 유효기간(FG_CACHE_TTL) 동안 재사용.
    """
    # 최신 캐시 로드 후 검증
    _load_fng_cache()
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
        _save_fng_cache()
        return val
    except Exception as e:
        logger.warning("get_fear_and_greed() 실패: %s", e)
        return FNG_CACHE["value"]


