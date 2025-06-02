# trading_bot/db_helpers.py

import sqlite3
from typing import Any, Callable
import pandas as pd
import logging

from trading_bot.config import DB_FILE

logger = logging.getLogger(__name__)


def with_db(fn: Callable[..., Any]):
    """
    SQLite 데이터베이스 연결을 자동으로 열고 닫아 주는 데코레이터.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        try:
            result = fn(conn, *args, **kwargs)
            conn.commit()
            return result
        finally:
            conn.close()
    return wrapper


@with_db
def init_db(conn: sqlite3.Connection) -> None:
    """
    DB 파일이 없으면 생성하고, 필요한 테이블을 만든다.
    """
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS account (
      id INTEGER PRIMARY KEY CHECK(id=1),
      krw REAL,
      btc REAL,
      avg_price REAL
    );
    CREATE TABLE IF NOT EXISTS indicator_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts REAL,
      sma REAL,
      atr REAL,
      vol20 REAL,
      macd_diff REAL,
      price REAL,
      fear_greed INTEGER
    );
    CREATE TABLE IF NOT EXISTS trade_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts REAL,
      decision TEXT,
      percentage REAL,
      pattern TEXT,
      reason TEXT,
      btc_balance REAL,
      krw_balance REAL,
      avg_price REAL,
      price REAL,
      mode TEXT,
      reflection TEXT
    );
    """)


@with_db
def load_account(conn: sqlite3.Connection) -> tuple[float, float, float]:
    """
    account 테이블에서 잔고(krw, btc, avg_price)를 불러온다.
    없으면 초기값(30000, 0, 0)을 삽입 후 리턴.
    """
    row = conn.execute("SELECT krw, btc, avg_price FROM account WHERE id=1").fetchone()
    if row:
        return row["krw"], row["btc"], row["avg_price"]
    conn.execute("INSERT INTO account VALUES(1, 30000, 0, 0)")
    return 30000.0, 0.0, 0.0


@with_db
def save_account(conn: sqlite3.Connection, krw: float, btc: float, avg_price: float) -> None:
    """
    현재 account 값을 DB에 업데이트.
    """
    conn.execute(
        "UPDATE account SET krw=?, btc=?, avg_price=? WHERE id=1",
        (krw, btc, avg_price)
    )


@with_db
def log_indicator(conn: sqlite3.Connection, ts: float, sma: float, atr: float,
                  vol20: float, macd_diff: float, price: float, fear_greed: int) -> None:
    """
    매 호출 시점의 지표를 indicator_log 테이블에 기록.
    """
    conn.execute(
        """INSERT INTO indicator_log
           (ts, sma, atr, vol20, macd_diff, price, fear_greed)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ts, sma, atr, vol20, macd_diff, price, fear_greed)
    )


@with_db
def log_trade(conn: sqlite3.Connection, ts: float, decision: str, percentage: float,
              pattern: str, reason: str, btc_balance: float, krw_balance: float,
              avg_price: float, price: float, mode: str, reflection: str) -> None:
    """
    매매가 이루어질 때마다 trade_log 테이블에 기록.
    """
    conn.execute(
        """INSERT INTO trade_log
           (ts, decision, percentage, pattern, reason,
            btc_balance, krw_balance, avg_price, price, mode, reflection)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ts, decision, percentage, pattern, reason,
         btc_balance, krw_balance, avg_price, price, mode, reflection)
    )


def get_recent_trades(limit: int = 20) -> pd.DataFrame:
    """
    trade_log 테이블에서 최근 limit개 행을 DataFrame으로 반환.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT ts, decision, percentage, reason, btc_balance, krw_balance, avg_price, price "
        "FROM trade_log ORDER BY ts DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    cols = [col[0] for col in cur.description]
    conn.close()
    return pd.DataFrame(rows, columns=cols)
