#!/usr/bin/env bash
set -euo pipefail

# 1) 리포지토리 최신화
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 2) 가상환경 활성화
source "$PROJECT_DIR/venv/bin/activate"

# 3) 의존성 설치 (필요 시)
pip install --upgrade pip
pip install -r requirements.txt

# 4) 자동매매 스크립트 실행
#    전달받은 모든 인자($@)를 python3 -m trading_bot.main 에 넘겨 줍니다.
#    로그는 trading_bot/logs/cron.log 에 append
python3 -m trading_bot.main "$@" >> "$PROJECT_DIR/trading_bot/logs/cron.log" 2>&1

