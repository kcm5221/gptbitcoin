"""Utility functions for .env parameter tuning."""

from pathlib import Path
import re
from typing import Dict


def parse_suggestion(text: str) -> Dict[str, str]:
    """AI 응답 문자열에서 "KEY=VALUE" 쌍을 모두 추출해 dict로 반환."""
    pairs = re.findall(r"([A-Z0-9_]+)\s*=\s*([^\s#]+)", text)
    return {k.strip(): v.strip() for k, v in pairs}


def update_env_vars(suggestions: Dict[str, str], env_path: Path) -> None:
    """.env 파일을 suggestions 값으로 업데이트 후 덮어쓴 줄 끝에 '# [AI-TUNED]'를 추가."""
    if not suggestions:
        return

    text = env_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    updated_keys = set()
    new_lines = []

    for line in lines:
        replaced = False
        for key, val in suggestions.items():
            if re.match(rf"\s*{re.escape(key)}\s*=", line):
                indent = re.match(r"\s*", line).group(0)
                comment = ""
                if "#" in line:
                    comment = line.split("#", 1)[1].strip()
                new_line = f"{indent}{key}={val}"
                if comment:
                    new_line += f" #{comment} # [AI-TUNED]"
                else:
                    new_line += " # [AI-TUNED]"
                new_lines.append(new_line)
                updated_keys.add(key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for key, val in suggestions.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val} # [AI-TUNED]")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
