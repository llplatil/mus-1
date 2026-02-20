from __future__ import annotations

import sqlite3


def ensure_ml_tables(con: sqlite3.Connection) -> None:
    """
    Lightweight DB-first tables used by the Streamlit app.

    We keep these in SQLite directly (no ORM) so the web UI can evolve quickly
    without entangling core MUS1 schema/migrations.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_frame_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          run_path TEXT NOT NULL,
          video_path TEXT NOT NULL,
          frame_idx INTEGER,
          overlay_path TEXT,
          zone_json TEXT,
          metric REAL,
          label TEXT,
          notes TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_frame_reviews_unique
        ON ml_frame_reviews(kind, run_path, video_path, frame_idx, overlay_path)
        """
    )
    con.commit()

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_training_frame_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          run_path TEXT NOT NULL,
          video_path TEXT NOT NULL,
          frame_idx INTEGER NOT NULL,
          overlay_path TEXT,
          zone_json TEXT,
          score REAL,
          status TEXT NOT NULL DEFAULT 'queued',
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_training_frame_queue_unique
        ON ml_training_frame_queue(kind, run_path, video_path, frame_idx)
        """
    )
    con.commit()

