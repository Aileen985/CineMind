# db/pools.py
import sqlite3
from datetime import datetime
from config import POOL_DB_PATH


def get_conn():
    return sqlite3.connect(POOL_DB_PATH, timeout=10)


def init_table():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS hot_pool (
                movie_id INTEGER PRIMARY KEY,
                tmdb_id INTEGER,
                title TEXT,
                genres TEXT,
                popularity REAL,
                vote_average REAL,
                vote_count INTEGER,
                poster_path TEXT,
                created_at TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cold_pool (
                movie_id INTEGER PRIMARY KEY,
                tmdb_id INTEGER,
                title TEXT,
                genres TEXT,
                popularity REAL,
                vote_average REAL,
                vote_count INTEGER,
                poster_path TEXT,
                created_at TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pool_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')


# 别名（供 pool_builder.py 使用）
init_pools = init_table

def save_hot_pool(movies):
    seen = set()
    unique_movies = []
    for m in movies:
        movie_id = m.get("id")
        if movie_id and movie_id not in seen:
            seen.add(movie_id)
            unique_movies.append(m)

    with get_conn() as conn:
        conn.execute('DELETE FROM hot_pool')
        now = datetime.now().isoformat()
        for m in unique_movies:
            conn.execute('''
                INSERT OR REPLACE INTO hot_pool 
                (movie_id, tmdb_id, title, genres, popularity, vote_average, vote_count, poster_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                m["id"], m["id"], m.get("title", ""), m.get("genres", ""),
                m.get("popularity", 0.0), m.get("vote_average", 0.0), m.get("vote_count", 0),
                m.get("poster_path", ""), now
            ))


def save_cold_pool(movies):
    seen = set()
    unique_movies = []
    for m in movies:
        movie_id = m.get("id")
        if movie_id and movie_id not in seen:
            seen.add(movie_id)
            unique_movies.append(m)

    with get_conn() as conn:
        conn.execute('DELETE FROM cold_pool')
        now = datetime.now().isoformat()
        for m in unique_movies:
            conn.execute('''
                INSERT OR REPLACE INTO cold_pool 
                (movie_id, tmdb_id, title, genres, popularity, vote_average, vote_count, poster_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                m["id"], m["id"], m.get("title", ""), m.get("genres", ""),
                m.get("popularity", 0.0), m.get("vote_average", 0.0), m.get("vote_count", 0),
                m.get("poster_path", ""), now
            ))


def update_pool_meta(key, value):
    with get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO pool_meta (key, value) VALUES (?, ?)', (key, value))


def get_pool_meta(key):
    """从 pool_meta 表获取指定键的值"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT value FROM pool_meta WHERE key = ?', (key,))
        row = cur.fetchone()
        return row[0] if row else None


def get_hot_pool(limit=None):
    with get_conn() as conn:
        cur = conn.cursor()
        query = "SELECT * FROM hot_pool ORDER BY popularity DESC"
        if limit:
            query += f" LIMIT {limit}"
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]


def get_cold_pool(limit=None):
    with get_conn() as conn:
        cur = conn.cursor()
        query = "SELECT * FROM cold_pool ORDER BY popularity ASC"
        if limit:
            query += f" LIMIT {limit}"
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]


def get_pool_stats():
    """获取池子统计信息"""
    hot_count = get_pool_meta('hot_count')
    cold_count = get_pool_meta('cold_count')
    last_build = get_pool_meta('last_build')
    return {
        'hot_count': int(hot_count) if hot_count else 0,
        'cold_count': int(cold_count) if cold_count else 0,
        'last_build': last_build
    }