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
        # A single write lock covers version inspection, DDL and version update.
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            raise ValueError("database newer than application")
        scripts = []
        if version == 0:
            scripts.append("schema.sql")
        if version < 2:
            scripts.append("migration_v2.sql")
        for name in scripts:
            # These packaged migrations contain plain SQL statements, no triggers.
            sql = Path(__file__).with_name(name).read_text(encoding="utf-8-sig")
            for statement in sql.split(";"):
                if statement.strip():
                    conn.execute(statement)
