import json
import logging
import re
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def read_env_vars(dotenv_path: Path) -> Dict[str, str]:
    """Load key-value pairs from ``dotenv_path`` ignoring comments."""
    result: Dict[str, str] = {}
    if not dotenv_path.exists():
        return result
    with dotenv_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, _, val = stripped.partition("=")
            result[key] = val.split("#", 1)[0].strip()
    return result


def parse_suggestion(text: str) -> Dict[str, str]:
    """Extract KEY=VALUE pairs from AI text or embedded JSON."""
    if not text:
        return {}
    # try JSON first
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    pairs = re.findall(r"([A-Z_]+)\s*=\s*([0-9\.]+)", text)
    return {k: v for k, v in pairs}


def update_env_vars(suggestions: Dict[str, str], dotenv_path: Path) -> None:
    """Overwrite keys in ``dotenv_path`` with ``suggestions`` while preserving order and comments."""
    if not suggestions:
        return

    if dotenv_path.exists():
        lines = dotenv_path.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = []
    new_lines = []
    handled = set()

    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, rest = line.split("=", 1)
            k = key.strip()
            if k in suggestions:
                value_part, comment_part = (rest.split("#", 1) + [""])[0:2]
                old_val = value_part.strip()
                new_val = suggestions[k]
                comment = ("#" + comment_part) if comment_part else ""
                new_lines.append(f"{k}={new_val}{(' ' + comment.strip()) if comment else ''}\n")
                logger.info("[AI-TUNED] %s: %s → %s", k, old_val, new_val)
                handled.add(k)
                continue
        new_lines.append(line)

    for k, v in suggestions.items():
        if k not in handled:
            new_lines.append(f"{k}={v}\n")
            logger.info("[AI-TUNED] %s: (new) → %s", k, v)

    dotenv_path.write_text("".join(new_lines), encoding="utf-8")
