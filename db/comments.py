# db/comments.py
import sqlite3
import time
from config import RATING_DB_PATH

def get_conn():
    return sqlite3.connect(RATING_DB_PATH, timeout=10)

def init_table():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                tmdbId INTEGER NOT NULL,
                comment TEXT,
                timestamp INTEGER NOT NULL
            )
        ''')

def save_comment(username, tmdb_id, comment):
    with get_conn() as conn:
        timestamp = int(time.time())
        conn.execute('''
            INSERT OR REPLACE INTO comments (username, tmdbId, comment, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (username, tmdb_id, comment, timestamp))
    return True

def get_my_comment(username, tmdb_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT comment FROM comments WHERE username = ? AND tmdbId = ?', (username, tmdb_id))
        row = cur.fetchone()
        return row[0] if row else None