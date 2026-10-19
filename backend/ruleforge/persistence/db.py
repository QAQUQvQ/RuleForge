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

def initialize(path: Path, *, target_version=4):
    with connect(path) as conn:
        # A single write lock covers version inspection, DDL and version update.
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if target_version not in (3, 4) or version > target_version:
            raise ValueError("database newer than application")
        scripts = []
        if version == 0:
            scripts.append("schema.sql")
        if version < 2:
            scripts.append("migration_v2.sql")
        if version < 3:
            scripts.append("migration_v3.sql")
        if version < 4 and target_version == 4:
            scripts.append("migration_v4.sql")
        for name in scripts:
            # These packaged migrations contain plain SQL statements, no triggers.
            sql = Path(__file__).with_name(name).read_text(encoding="utf-8-sig")
            for statement in sql.split(";"):
                if statement.strip():
                    conn.execute(statement)


def rollback_v3(path: Path):
    """Lossless downgrade only before M2 data exists. Never discard user data."""
    with connect(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('rollback requires v3')
        if any(conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
               for table in ('runtime_grants', 'character_equipment')):
            raise ValueError('M2 data exists; retain v3 or restore an explicit backup')
        # Characters with empty inventories still contain M2 fields.
        if conn.execute("SELECT 1 FROM characters WHERE json_extract(state_json,'$.class_ref') IS NOT NULL").fetchone():
            raise ValueError('M2 characters exist; downgrade refused')
        conn.execute('DROP TABLE character_equipment')
        conn.execute('DROP TABLE runtime_grants')
        conn.execute('PRAGMA user_version=2')
