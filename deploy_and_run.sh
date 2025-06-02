#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# deploy_and_run.sh (업데이트된 버전)
# - 프로젝트 최신화 → venv 활성화 → 의존성 설치 → 봇 실행
# ─────────────────────────────────────────────────────────

# 1) 리포지토리 루트로 이동
cd /home/ubuntu/gptbitcoin

# 2) 가상환경 활성화
source /home/ubuntu/gptbitcoin/venv/bin/activate

# 3) 필요 시 의존성 설치/업그레이드
pip install --upgrade pip
pip install -r requirements.txt

# ─────────────────────────────────────────
# 4) 자동매매 스크립트 실행 (인트라데이 모드)
#    → 출력을 logs/cron.log 에 덧붙이기
# ─────────────────────────────────────────
python3 -m trading_bot.main --mode intraday \
    >> /home/ubuntu/gptbitcoin/logs/cron.log 2>&1

