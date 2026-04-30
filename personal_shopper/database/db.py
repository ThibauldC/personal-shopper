import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from personal_shopper.database.schema import SCHEMA_SQL


def init_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


@contextmanager
def get_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
