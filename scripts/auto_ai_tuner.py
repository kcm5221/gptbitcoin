"""CLI script to automatically tune .env parameters using AI suggestions."""

from pathlib import Path
from dotenv import load_dotenv

from trading_bot.ai_helpers import ask_ai_parameter_tuning
from trading_bot.env_utils import parse_suggestion, update_env_vars

ENV_PATH = Path(".env")


def main() -> None:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        print(".env 파일을 찾을 수 없습니다.")
        return

    for attempt in range(3):
        reply = ask_ai_parameter_tuning()
        if not reply:
            print("AI 응답을 받지 못했습니다.")
            break

        print(f"AI 제안({attempt+1}): {reply}")

        if "더 이상 변경할 사항 없음" in reply:
            print("AI가 더 이상 변경할 사항이 없다고 응답했습니다.")
            break

        params = parse_suggestion(reply)
        if not params:
            print("파싱된 파라미터가 없습니다. 다음 반복을 시도합니다.")
            continue

        update_env_vars(params, ENV_PATH)
        load_dotenv(ENV_PATH, override=True)

    print("auto_ai_tuner 완료")


if __name__ == "__main__":
    main()
