import sqlite3
import logging
from typing import Any, Callable
import pandas as pd

from trading_bot.config import DB_FILE, INITIAL_KRW

logger = logging.getLogger(__name__)


def with_db(fn: Callable[..., Any]):
    """
    SQLite 데이터베이스 연결을 자동으로 열고 닫아 주는 데코레이터.
    - timeout=5초 대기
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                result = fn(conn, *args, **kwargs)
                conn.commit()
                return result
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            logger.exception(f"with_db: DB 연결 실패 또는 잠김: {e}")
            raise
        except Exception as e:
            logger.exception(f"with_db: 예외 발생: {e}")
            raise
    return wrapper


@with_db
def init_db(conn: sqlite3.Connection) -> None:
    """
    DB 파일이 없으면 생성하고, 필요한 테이블을 만든다.
    """
    try:
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
          reflection_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS reflection_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL,
          reflection TEXT
        );
        """)
    except Exception as e:
        logger.exception(f"init_db: 스키마 생성 중 예외 발생: {e}")
        raise


@with_db
def load_account(conn: sqlite3.Connection) -> tuple[float, float, float]:
    """
    account 테이블에서 잔고(krw, btc, avg_price)를 불러온다.
    없으면 초기값(INITIAL_KRW, 0, 0)을 삽입 후 리턴.
    """
    try:
        row = conn.execute("SELECT krw, btc, avg_price FROM account WHERE id=1").fetchone()
        if row:
            return row["krw"], row["btc"], row["avg_price"]
        conn.execute(
            "INSERT INTO account (id, krw, btc, avg_price) VALUES (1, ?, 0, 0)",
            (INITIAL_KRW,)
        )
        return INITIAL_KRW, 0.0, 0.0
    except Exception as e:
        logger.exception(f"load_account: DB 조회/생성 중 예외 발생: {e}")
        return INITIAL_KRW, 0.0, 0.0


@with_db
def save_account(conn: sqlite3.Connection, krw: float, btc: float, avg_price: float) -> None:
    """
    현재 account 값을 DB에 업데이트.
    """
    try:
        conn.execute(
            "UPDATE account SET krw=?, btc=?, avg_price=? WHERE id=1",
            (krw, btc, avg_price)
        )
    except Exception as e:
        logger.exception(f"save_account: 예외 발생: {e}")


@with_db
def log_indicator(conn: sqlite3.Connection, ts: float, sma: float, atr: float,
                  vol20: float, macd_diff: float, price: float, fear_greed: int) -> None:
    """
    매 호출 시점의 지표를 indicator_log 테이블에 기록.
    """
    try:
        conn.execute(
            """INSERT INTO indicator_log
               (ts, sma, atr, vol20, macd_diff, price, fear_greed)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, sma, atr, vol20, macd_diff, price, fear_greed)
        )
    except Exception as e:
        logger.exception(f"log_indicator: 예외 발생: {e}")


@with_db
def log_trade(conn: sqlite3.Connection, ts: float, decision: str, percentage: float,
              pattern: str, reason: str, btc_balance: float, krw_balance: float,
              avg_price: float, price: float, mode: str, reflection_id: int) -> None:
    """
    매매가 이루어질 때마다 trade_log 테이블에 기록.
    """
    try:
        conn.execute(
            """INSERT INTO trade_log
               (ts, decision, percentage, pattern, reason,
                btc_balance, krw_balance, avg_price, price, mode, reflection_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, decision, percentage, pattern, reason,
             btc_balance, krw_balance, avg_price, price, mode, reflection_id)
        )
    except Exception as e:
        logger.exception(f"log_trade: 예외 발생: {e}")


@with_db
def log_reflection(conn: sqlite3.Connection, ts: float, reflection: str) -> int:
    """
    AI 반성문(reflection)을 reflection_log 테이블에 기록하고, 새로 만들어진 id를 반환.
    """
    try:
        cur = conn.execute(
            "INSERT INTO reflection_log (ts, reflection) VALUES (?, ?)",
            (ts, reflection)
        )
        return cur.lastrowid
    except Exception as e:
        logger.exception(f"log_reflection: 예외 발생: {e}")
        return 0


@with_db
def get_last_reflection_ts(conn: sqlite3.Connection) -> float:
    """
    가장 최근에 저장된 reflection_log의 ts를 반환.
    없으면 0을 반환.
    """
    try:
        row = conn.execute(
            "SELECT ts FROM reflection_log ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return row["ts"] if row else 0.0
    except Exception as e:
        logger.exception(f"get_last_reflection_ts: 예외 발생: {e}")
        return 0.0


@with_db
def get_recent_trades(conn: sqlite3.Connection, limit: int = 20) -> pd.DataFrame:
    """
    trade_log 테이블에서 최근 limit개 행을 DataFrame으로 반환.
    """
    try:
        cur = conn.execute(
            "SELECT ts, decision, percentage, reason, btc_balance, krw_balance, avg_price, price "
            "FROM trade_log ORDER BY ts DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        cols = [col[0] for col in cur.description]
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        logger.exception(f"get_recent_trades: 예외 발생: {e}")
        return pd.DataFrame(columns=[
            "ts", "decision", "percentage", "reason",
            "btc_balance", "krw_balance", "avg_price", "price"
        ])


@with_db
def has_indicator(conn: sqlite3.Connection, ts: float) -> bool:
    """
    특정 ts(타임스탬프) 이상인 indicator_log 레코드가 이미 있는지 확인.
    """
    try:
        row = conn.execute(
            "SELECT 1 FROM indicator_log WHERE ts>=? LIMIT 1",
            (ts,)
        ).fetchone()
        return row is not None
    except Exception as e:
        logger.exception(f"has_indicator: 예외 발생: {e}")
        return False
