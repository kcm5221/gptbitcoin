# ai_tuning_scheduler.py

import os
import json
import sqlite3
import pandas as pd
from openai import OpenAI

# ──────────────────────────────────────────────────────────────
# 설정: 환경 변수 읽기
# ──────────────────────────────────────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_KEY)

# 그리드 탐색 결과 CSV/JSON 경로
CSV_PATH  = "parameter_tuning_results.csv"
JSON_PATH = "parameter_tuning_results.json"

# AI 제안 결과를 저장할 파일
OUTPUT_TXT = "ai_tuning_suggestion.txt"

# ──────────────────────────────────────────────────────────────
# Helper: 상위 N개 결과를 불러와 요약 JSON 반환
# ──────────────────────────────────────────────────────────────
def load_top_results(csv_path: str, top_n: int = 10) -> list[dict]:
    """
    CSV에서 그리드 탐색 결과를 읽어,
    total_return_pct 기준으로 상위 top_n개 행을 dict 리스트로 반환합니다.
    """
    df = pd.read_csv(csv_path)
    df_top = df.sort_values(by="total_return_pct", ascending=False).head(top_n)
    return df_top.to_dict(orient="records")

# ──────────────────────────────────────────────────────────────
# Helper: 현재 성과 지표(Trade 로그 기반) 계산 (선택적)
# ──────────────────────────────────────────────────────────────
def compute_overall_metrics(db_path: str) -> dict:
    """
    만약 'trade_log' 기반의 종합 성과 지표(승률, 평균 수익률 등)를 함께 AI에게 전달하고 싶다면,
    아래 함수를 활용해 'metrics' 딕셔너리를 생성할 수 있습니다.
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT ts, decision, percentage, reason, btc_balance, krw_balance, avg_price, price FROM trade_log",
        conn
    )
    conn.close()

    # 매도 거래만 필터
    sell_df = df[df["decision"] == "sell"].copy()
    if sell_df.empty:
        return {
            "total_trades": len(df),
            "total_sells": 0,
            "win_rate": None,
            "avg_profit_pct": None,
            "avg_loss_pct": None
        }

    sell_df["pnl_pct"] = (sell_df["price"] - sell_df["avg_price"]) / sell_df["avg_price"] * 100
    total_sells = len(sell_df)
    winning_sells = (sell_df["pnl_pct"] > 0).sum()
    win_rate = round(winning_sells / total_sells * 100, 2)

    avg_profit_pct = round(sell_df[sell_df["pnl_pct"] > 0]["pnl_pct"].mean(), 2) \
                     if any(sell_df["pnl_pct"] > 0) else None
    avg_loss_pct = round(sell_df[sell_df["pnl_pct"] <= 0]["pnl_pct"].mean(), 2) \
                   if any(sell_df["pnl_pct"] <= 0) else None

    return {
        "total_trades": len(df),
        "total_sells": total_sells,
        "win_rate": win_rate,
        "avg_profit_pct": avg_profit_pct,
        "avg_loss_pct": avg_loss_pct
    }

# ──────────────────────────────────────────────────────────────
# 메인: AI에게 파라미터 튜닝 제안 요청
# ──────────────────────────────────────────────────────────────
def request_ai_tuning_suggestion():
    # 1) CSV에서 상위 N개 그리드 결과 불러오기
    if not os.path.exists(CSV_PATH):
        print(f"CSV 파일을 찾을 수 없습니다: {CSV_PATH}")
        return

    top_results = load_top_results(CSV_PATH, top_n=10)

    # 선택적으로 DB 기반 성과 지표를 같이 보낼 수도 있음
    # from config import DB_FILE
    # metrics = compute_overall_metrics(str(DB_FILE))
    # 여기에 metrics를 포함하려면 아래 프롬프트에 추가로 삽입

    # 2) AI에게 보낼 프롬프트 구성
    prompt = (
        "You are a quantitative trading assistant.\n"
        "Based on the following backtest top 10 parameter results (JSON format),\n"
        "Please suggest how to adjust SMA window, ATR window, and volume spike threshold\n"
        "to potentially improve performance in the next period. Explain your reasoning briefly.\n\n"
        f"Top 10 results:\n{json.dumps(top_results, indent=2)}\n"
        # f"Overall performance metrics:\n{json.dumps(metrics, indent=2)}\n"
        "\nRespond in ≤200 tokens in plain text."
    )

    # 3) OpenAI API 호출
    try:
        response = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        suggestion = response.choices[0].message.content.strip()
    except Exception as e:
        print("AI 요청 중 오류 발생:", e)
        return

    # 4) 결과를 파일에 저장
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(suggestion)

    print(f"AI 제안이 '{OUTPUT_TXT}'에 저장되었습니다.")
    print("\n=== AI Suggestion ===")
    print(suggestion)


if __name__ == "__main__":
    request_ai_tuning_suggestion()
