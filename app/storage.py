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
  normalized_brand TEXT,
  normalized_model TEXT,
  normalized_storage_gb INTEGER,
  normalized_color TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)

    # lightweight migration path for existing DBs
    for ddl in [
        "ALTER TABLE deals ADD COLUMN normalized_brand TEXT",
        "ALTER TABLE deals ADD COLUMN normalized_model TEXT",
        "ALTER TABLE deals ADD COLUMN normalized_storage_gb INTEGER",
        "ALTER TABLE deals ADD COLUMN normalized_color TEXT",
    ]:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            # column already exists
            pass

    conn.commit()
    return conn

def upsert_deal(conn, deal: dict):
    conn.execute(
        """INSERT OR IGNORE INTO deals(
               source,title,url,price,votes,posted_at,score,reasons,
               normalized_brand,normalized_model,normalized_storage_gb,normalized_color
           )
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            deal.get("source"),
            deal.get("title"),
            deal.get("url"),
            deal.get("price"),
            deal.get("votes"),
            deal.get("posted_at"),
            deal.get("score"),
            deal.get("reasons"),
            deal.get("normalized_brand"),
            deal.get("normalized_model"),
            deal.get("normalized_storage_gb"),
            deal.get("normalized_color"),
        ),
    )
    conn.commit()

def top_deals(conn, min_score=55, limit=10, days=7):
    cur = conn.execute(
        """SELECT source,title,url,price,votes,score,reasons
           FROM deals
           WHERE score >= ?
             AND datetime(created_at) >= datetime('now', ?)
           ORDER BY score DESC, id DESC
           LIMIT ?""",
        (min_score, f"-{int(days)} days", limit),
    )
    return cur.fetchall()
