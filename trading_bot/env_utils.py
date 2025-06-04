import json
import re
import logging
from pathlib import Path
from typing import Dict
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

STRATEGY_KEYS = [
    "SMA_WINDOW",
    "ATR_WINDOW",
    "VOLUME_SPIKE_THRESHOLD",
    "RSI_OVERRIDE",
    "MACD_1H_THRESHOLD",
    "FG_EXTREME_FEAR",
]


def parse_suggestion(text: str) -> Dict[str, str]:
    """Extract KEY=VALUE pairs or JSON from AI response text."""
    text = text.strip()
    # JSON 형식("{"...") 시도
    if text.startswith("{") and text.endswith("}" ):
        try:
            data = json.loads(text)
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass

    pairs = re.findall(r"([A-Z][A-Z0-9_]*)\s*[:=]\s*([^\s,;]+)", text)
    return {k: v for k, v in pairs}


def update_env_vars(suggestions: Dict[str, str], dotenv_path: Path) -> None:
    """Update .env file with suggested values while keeping comments and order."""
    if not suggestions or not dotenv_path.exists():
        return

    lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    remaining = suggestions.copy()

    for line in lines:
        m = re.match(r"^([A-Z0-9_]+)=([^#\n]*)(.*)$", line)
        if m:
            key, val, comment = m.groups()
            if key in remaining:
                new_val = remaining.pop(key)
                old_val = val.rstrip()
                trailing = val[len(old_val):]
                if old_val != new_val:
                    logger.info(f"[AI-TUNED] {key}: {old_val} → {new_val}")
                line = f"{key}={new_val}{trailing}{comment}"
        updated.append(line)

    for key, val in remaining.items():
        logger.info(f"[AI-TUNED] {key}: (new) → {val}")
        updated.append(f"{key}={val}")

    dotenv_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def load_strategy_params(dotenv_path: Path) -> Dict[str, str]:
    """Load selected strategy parameters from .env as a dictionary."""
    env = dotenv_values(dotenv_path)
    return {k: env.get(k, "") for k in STRATEGY_KEYS}
