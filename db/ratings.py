import sqlite3
import time
from config import RATING_DB_PATH

def get_conn():
    return sqlite3.connect(RATING_DB_PATH, timeout=10)

def init_table():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                tmdbId INTEGER NOT NULL,
                rating REAL NOT NULL,
                timestamp INTEGER NOT NULL,
                UNIQUE(username, tmdbId)
            )
        ''')

def save_rating(username, tmdbId, rating):
    with get_conn() as conn:
        timestamp = int(time.time())
        conn.execute('''
            INSERT INTO ratings (username, tmdbId, rating, timestamp)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, tmdbId) DO UPDATE SET rating=?, timestamp=?
        ''', (username, tmdbId, rating, timestamp, rating, timestamp))
    return True

def get_user_ratings(username):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT tmdbId, rating, timestamp FROM ratings WHERE username = ? ORDER BY timestamp DESC', (username,))
        return cur.fetchall()

def get_rating_stats(username):
    ratings = get_user_ratings(username)
    if not ratings:
        return None
    total = len(ratings)
    avg = sum(r[1] for r in ratings) / total
    high_cnt = sum(1 for r in ratings if r[1] > 4)
    return {'total': total, 'avg': avg, 'high_cnt': high_cnt}

def get_user_stats(username):
    """获取用户评分统计"""
    return get_rating_stats(username)

def get_my_rating(username, tmdbId):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT rating FROM ratings WHERE username = ? AND tmdbId = ?', (username, tmdbId))
        row = cur.fetchone()
        return row[0] if row else None