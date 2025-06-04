import logging
from pathlib import Path

import pandas as pd

from trading_bot.data_fetcher import fetch_data_15m
from trading_bot.ai_helpers import ask_ai_parameter_tuning
from trading_bot.env_utils import parse_suggestion, update_env_vars, load_strategy_params, STRATEGY_KEYS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def run_parameter_tuning(max_rounds: int = 3) -> None:
    df = fetch_data_15m().tail(100)
    for i in range(max_rounds):
        params = load_strategy_params(ENV_PATH)
        resp = ask_ai_parameter_tuning(df, params)
        if not resp or "더 이상 변경할 사항 없음" in resp:
            logger.info("AI가 더 이상 변경할 사항 없다고 응답")
            break
        suggestions = parse_suggestion(resp)
        if not suggestions:
            logger.info("추출된 파라미터 없음")
            break
        before = load_strategy_params(ENV_PATH)
        update_env_vars(suggestions, ENV_PATH)
        after = load_strategy_params(ENV_PATH)
        if before == after:
            logger.info("파라미터 변경 사항 없음")
            break
    logger.info("튜닝 종료")


if __name__ == "__main__":
    run_parameter_tuning()
