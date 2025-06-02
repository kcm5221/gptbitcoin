# parameter_tuning.py

import pandas as pd
import numpy as np
import itertools
import json
from ta.trend import SMAIndicator, MACD
from ta.volatility import AverageTrueRange

# ──────────────────────────────────────────────────────────────
# 1) CSV 데이터 로드
# ──────────────────────────────────────────────────────────────
def load_historical_ohlcv(csv_path: str) -> pd.DataFrame:
    """
    CSV 파일에서 과거 15분봉 OHLCV 데이터를 불러와 DataFrame으로 반환.
    'datetime' 컬럼을 인덱스로 지정하고, 올림차순 정렬합니다.
    """
    df = pd.read_csv(csv_path, parse_dates=['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    df.set_index('datetime', inplace=True)
    return df

# ──────────────────────────────────────────────────────────────
# 2) 지표 계산 함수
# ──────────────────────────────────────────────────────────────
def add_indicators(df: pd.DataFrame, sma_window: int, atr_window: int) -> pd.DataFrame:
    """
    DataFrame에 SMA, ATR, 20봉 평균 거래량, MACD-Diff 컬럼을 추가하여 반환합니다.
    """
    tmp = df.copy()
    tmp['sma']      = SMAIndicator(tmp['close'], sma_window, True).sma_indicator()
    tmp['atr']      = AverageTrueRange(tmp['high'], tmp['low'], tmp['close'], atr_window, True).average_true_range()
    tmp['vol20']    = tmp['volume'].rolling(20).mean()
    tmp['macd_diff']= MACD(tmp['close'], fillna=True).macd_diff()
    return tmp.dropna()

# ──────────────────────────────────────────────────────────────
# 3) 백테스트 로직 (규칙 기반 매매 시뮬레이션)
# ──────────────────────────────────────────────────────────────
def backtest_strategy(df: pd.DataFrame, sma_window: int, atr_window: int, volume_threshold: float) -> dict:
    """
    주어진 지표가 추가된 DataFrame을 바탕으로, 규칙 기반 매수/매도 시뮬레이션을 수행한 뒤,
    성과 지표를 계산해 반환합니다.

    - 초기 자본: 1,000,000 KRW
    - 전량 진입/전량 청산 방식 가정
    """
    balance_krw = 1_000_000.0
    balance_btc = 0.0
    avg_price   = 0.0

    trade_records = []

    for idx, row in df.iterrows():
        price   = row['close']
        sma     = row['sma']
        vol20   = row['vol20']
        volume  = row['volume']

        # 거래량 스파이크 여부
        is_vol_spike = (vol20 > 0) and (volume >= vol20 * volume_threshold)

        # 매수 조건: 종가 > SMA + 거래량 스파이크
        buy_signal = (price > sma) and is_vol_spike and (balance_krw > 0)
        # 매도 조건: 보유 중이고 (익절 ≥+5% 또는 손절 ≤−6%)
        sell_signal = (balance_btc > 0) and ((price >= avg_price * 1.05) or (price <= avg_price * 0.94))

        # 매수
        if buy_signal:
            balance_btc  = balance_krw / price
            avg_price    = price
            balance_krw  = 0.0
            trade_records.append({
                'datetime': idx, 'type': 'buy', 'price': price,
                'btc': balance_btc, 'krw': balance_krw
            })

        # 매도
        elif sell_signal:
            balance_krw = balance_btc * price
            balance_btc = 0.0
            trade_records.append({
                'datetime': idx, 'type': 'sell', 'price': price,
                'btc': balance_btc, 'krw': balance_krw
            })

    # 성과 지표 계산
    trades_df    = pd.DataFrame(trade_records)
    total_trades = len(trades_df)
    total_sells  = len(trades_df[trades_df['type'] == 'sell'])

    if total_sells > 0:
        sell_stats    = []
        last_buy_price = None
        for _, trade in trades_df.iterrows():
            if trade['type'] == 'buy':
                last_buy_price = trade['price']
            elif trade['type'] == 'sell' and last_buy_price is not None:
                pnl_pct = (trade['price'] - last_buy_price) / last_buy_price * 100
                sell_stats.append(pnl_pct)
                last_buy_price = None

        winning_sells  = sum(1 for pnl in sell_stats if pnl > 0)
        win_rate       = winning_sells / total_sells * 100
        avg_profit_pct = np.mean([pnl for pnl in sell_stats if pnl > 0]) if any(pnl > 0 for pnl in sell_stats) else 0
        avg_loss_pct   = np.mean([pnl for pnl in sell_stats if pnl <= 0]) if any(pnl <= 0 for pnl in sell_stats) else 0
    else:
        win_rate       = 0.0
        avg_profit_pct = 0.0
        avg_loss_pct   = 0.0

    # 최종 자본 (보유 BTC는 마지막 종가로 현금 환산)
    final_balance     = balance_krw + balance_btc * df['close'].iloc[-1]
    total_return_pct  = (final_balance - 1_000_000) / 1_000_000 * 100

    return {
        'sma_window': sma_window,
        'atr_window': atr_window,
        'volume_threshold': volume_threshold,
        'total_trades': total_trades,
        'total_sells': total_sells,
        'win_rate': round(win_rate, 2),
        'avg_profit_pct': round(avg_profit_pct, 2),
        'avg_loss_pct': round(avg_loss_pct, 2),
        'total_return_pct': round(total_return_pct, 2)
    }

# ──────────────────────────────────────────────────────────────
# 4) 파라미터 그리드 탐색
# ──────────────────────────────────────────────────────────────
def grid_search_parameters(df: pd.DataFrame, sma_range: list[int], atr_range: list[int], vol_thresholds: list[float]) -> pd.DataFrame:
    """
    주어진 파라미터 후보 그룹에 대해 백테스트를 수행하고, 결과를 DataFrame으로 반환합니다.
    """
    results = []
    for sma_w, atr_w, vol_th in itertools.product(sma_range, atr_range, vol_thresholds):
        df_ind = add_indicators(df, sma_w, atr_w)
        perf   = backtest_strategy(df_ind, sma_w, atr_w, vol_th)
        results.append(perf)

    return pd.DataFrame(results)

# ──────────────────────────────────────────────────────────────
# 5) 메인: 실행 예시
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 1) CSV로부터 과거 OHLCV 로드
    csv_path = "historical_ohlcv.csv"  # 이미 준비된 CSV 파일
    try:
        df_hist = load_historical_ohlcv(csv_path)
    except FileNotFoundError:
        print(f"CSV 파일이 없습니다: {csv_path}")
        exit(1)

    # 2) 파라미터 후보 범위 설정 (원하는 값으로 조정 가능)
    sma_candidates    = [20, 25, 30, 35, 40]       # SMA 기간 후보
    atr_candidates    = [10, 12, 14, 16]           # ATR 기간 후보
    vol_thresholds    = [1.5, 2.0, 2.5]            # 거래량 임계치 후보(볼륨/vol20)

    # 3) 그리드 탐색 수행
    grid_results = grid_search_parameters(df_hist, sma_candidates, atr_candidates, vol_thresholds)

    # 4) 결과 정렬해서 상위 10개 출력
    top_results = grid_results.sort_values(by='total_return_pct', ascending=False).head(10)
    print("Top 10 parameter combinations by Total Return:")
    print(top_results.to_string(index=False))

    # 5) 결과를 CSV 및 JSON으로 저장
    grid_results.to_csv("parameter_tuning_results.csv", index=False)
    grid_results.to_json("parameter_tuning_results.json", orient="records")

    print("\n결과가 parameter_tuning_results.csv 및 .json에 저장되었습니다.")
