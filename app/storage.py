import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  price REAL,
  votes INTEGER,
  posted_at TEXT,
  score REAL,
  reasons TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn

def upsert_deal(conn, deal: dict):
    conn.execute(
        """INSERT OR IGNORE INTO deals(source,title,url,price,votes,posted_at,score,reasons)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            deal.get("source"), deal.get("title"), deal.get("url"), deal.get("price"),
            deal.get("votes"), deal.get("posted_at"), deal.get("score"), deal.get("reasons"),
        ),
    )
    conn.commit()

def top_deals(conn, min_score=55, limit=10):
    cur = conn.execute(
        "SELECT source,title,url,price,votes,score,reasons FROM deals WHERE score >= ? ORDER BY score DESC, id DESC LIMIT ?",
        (min_score, limit),
    )
    return cur.fetchall()
