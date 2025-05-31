#!/usr/bin/env bash
set -euo pipefail

# 1) 리포지토리 최신화
cd /home/ubuntu/gptbitcoin

# 2) 가상환경 활성화
source /home/ubuntu/gptbitcoin/venv/bin/activate

# 3) 의존성 설치 (필요 시)
pip install --upgrade pip
pip install -r requirements.txt

# ─────────────────────────────────────────
# 4) 자동매매 스크립트 실행 (인트라데이 모드)
#    & 로그를 cron.log에 덧붙이기
# ─────────────────────────────────────────
python3 /home/ubuntu/gptbitcoin/autoTrading.py --mode intraday \
    >> /home/ubuntu/gptbitcoin/logs/cron.log 2>&1
