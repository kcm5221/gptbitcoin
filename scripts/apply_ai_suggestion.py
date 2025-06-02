# apply_ai_suggestion.py

import re

# ai_tuning_suggestion.txt 형식에 맞춰 조정한 예시
AI_SUGGEST_FILE = "ai_tuning_suggestion.txt"
ENV_FILE        = ".env"

def parse_suggestion(text: str) -> dict:
    """
    AI 제안 텍스트에서 'SMA window: 25', 'ATR window: 16', 'volume threshold: 1.5' 등
    숫자를 찾아서 딕셔너리로 반환합니다.
    """
    result = {}
    # 예: "SMA window of 25" 또는 "SMA window: 25"
    sma_match = re.search(r"SMA\s+window\s*(?:of|:)?\s*(\d+)", text, re.IGNORECASE)
    if sma_match:
        result["SMA_WIN"] = sma_match.group(1)

    atr_match = re.search(r"ATR\s+window\s*(?:of|:)?\s*(\d+)", text, re.IGNORECASE)
    if atr_match:
        result["ATR_WIN"] = atr_match.group(1)

    vol_match = re.search(r"volume\s+threshold\s*(?:of|:)?\s*([0-9]+\.?[0-9]*)", text, re.IGNORECASE)
    if vol_match:
        result["VOLUME_THRESHOLD"] = vol_match.group(1)

    return result

def apply_to_env(params: dict):
    """
    추출된 params(예: {'SMA_WIN':'25', 'ATR_WIN':'16', 'VOLUME_THRESHOLD':'1.5'})
    를 .env 파일에 덮어쓰기 합니다.
    """
    if not params:
        print("파라미터를 추출하지 못했습니다.")
        return

    # .env 내용을 한 줄씩 읽어서, 필요 항목만 변경
    lines = []
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            key = line.split("=", 1)[0]
            if key in params:
                f.write(f"{key}={params[key]}\n")
            else:
                f.write(line)

    print(f".env 파일이 다음 값으로 업데이트되었습니다: {params}")

if __name__ == "__main__":
    # 1) AI 제안 불러오기
    try:
        with open(AI_SUGGEST_FILE, "r", encoding="utf-8") as f:
            ai_text = f.read()
    except FileNotFoundError:
        print(f"{AI_SUGGEST_FILE} 파일을 찾을 수 없습니다.")
        exit(1)

    # 2) 텍스트 파싱
    new_params = parse_suggestion(ai_text)
    print("추출된 파라미터:", new_params)

    # 3) .env에 반영
    apply_to_env(new_params)
