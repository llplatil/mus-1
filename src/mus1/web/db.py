from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, List, Tuple


def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def fetchall(con: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
    cur = con.execute(sql, params)
    return list(cur.fetchall())


def one_col(con: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[str]:
    cur = con.execute(sql, params)
    return [str(r[0]) for r in cur.fetchall()]

