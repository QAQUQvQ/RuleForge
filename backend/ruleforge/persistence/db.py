import sqlite3
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

def initialize(path: Path):
    with connect(path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            raise ValueError("database newer than application")
        conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
