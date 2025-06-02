# fetch_ohlcv_to_csv.py

import time
import pandas as pd
import pyupbit

def fetch_15min_ohlcv(ticker: str, since: str = None, count: int = 200) -> pd.DataFrame:
    """
    PyUpbit을 통해 15분봉 OHLCV를 fetch합니다.
    - ticker: 종목 예) "KRW-BTC"
    - since: "YYYY-MM-DD HH:MM:SS" 또는 ISO 포맷 문자열. 이 시점 이전의 데이터를 불러옴.
    - count: 한 번에 가져올 봉 개수 (최대 200)
    """
    # PyUpbit get_ohlcv 함수는 `to` 파라미터를 쓰면, 해당 시각 직전 봉까지 count개 가져옵니다.
    if since:
        df = pyupbit.get_ohlcv(ticker, interval="minute15", to=since, count=count)
    else:
        # since가 지정되지 않으면, 최신부터 count개
        df = pyupbit.get_ohlcv(ticker, interval="minute15", count=count)
    return df

def build_full_history(ticker: str, start_dt: str, output_csv: str):
    """
    start_dt 이전 모든 (또는 start_dt 이후 최근) 15분봉을 모아서 CSV로 저장합니다.
    - ticker: "KRW-BTC" 등
    - start_dt: 불러오기를 시작할 기준 시각 (ISO 포맷). e.g. "2024-01-01 00:00:00"
    - output_csv: 저장할 파일명, 예) "historical_ohlcv.csv"
    """
    all_data = []

    # 1) 처음에는 최신 200개 봉을 가져옴 (since=None)
    df = fetch_15min_ohlcv(ticker)
    if df is None or df.empty:
        print("데이터를 가져오지 못했습니다.")
        return
    all_data.append(df)

    # 2) 가장 오래된 봉의 시각(인덱스)을 기준으로 루프 시작
    oldest_ts = df.index[0]  # DataFrame 처음 인덱스(가장 오래된 타임스탬프)
    print(f"첫 호출: 최신 200봉 중 가장 오래된 시각 = {oldest_ts}")

    # 3) start_dt(사용자가 원하는 시작 날짜) 이전까지 계속해서 가져옴
    #    연산량을 줄이려면 최대 반복 횟수 제한 가능
    while True:
        # 다음으로 불러올 'to' 시각: 현재 oldest_ts 직전
        to_str = (oldest_ts - pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        df = fetch_15min_ohlcv(ticker, since=to_str, count=200)
        if df is None or df.empty:
            print("더 이상 가져올 데이터가 없습니다.")
            break

        print(f"불러온 봉 개수: {len(df)} | 가장 오래된 시각 = {df.index[0]} → 모두 누적")

        all_data.append(df)
        oldest_ts = df.index[0]

        # 만약 이번에 가져온 가장 오래된 시각이 start_dt 이전이라면, 반복 종료
        if oldest_ts <= pd.to_datetime(start_dt):
            print(f"원하는 시작 시각({start_dt}) 이전의 데이터까지 확보했습니다.")
            break

        # API 호출 제한 완화(1초 휴식)
        time.sleep(1)

    # 4) 리스트에 쌓인 DataFrame들을 하나로 합치기
    full_df = pd.concat(all_data)
    # 인덱스를 기준(datetime)으로 중복 제거 후 정렬
    full_df = full_df[~full_df.index.duplicated(keep="first")]
    full_df = full_df.sort_index()

    # 5) 시작 시각 이전 데이터 제거 (start_dt 이후부터)
    full_df = full_df[full_df.index >= pd.to_datetime(start_dt)]

    # 6) CSV 파일로 저장
    full_df.to_csv(output_csv, index_label="datetime", columns=["open", "high", "low", "close", "volume"])
    print(f"CSV 저장 완료: {output_csv} (총 봉 개수: {len(full_df)})")

if __name__ == "__main__":
    # 예시: KRW-BTC, 2024년 1월 1일 00:00:00 이후부터
    ticker = "KRW-BTC"
    start_dt = "2024-12-01 00:00:00"  # 원하는 기간에 맞춰 바꿔 주세요
    output_csv = "historical_ohlcv.csv"

    build_full_history(ticker, start_dt, output_csv)
