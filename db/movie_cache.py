# db/movie_cache.py
import sqlite3
import json
from datetime import datetime, timedelta
from config import CLASSIFY_DB_PATH


def get_conn():
    return sqlite3.connect(CLASSIFY_DB_PATH, timeout=10)


def init_table():
    """创建所有电影缓存相关的表"""
    with get_conn() as conn:
        # 电影分类缓存（标签、风格）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS movie_classify (
                tmdb_id INTEGER PRIMARY KEY,
                title TEXT,
                genres TEXT,
                visual_style TEXT,
                atmosphere_style TEXT,
                tags TEXT,
                created_at TEXT
            )
        ''')

        # 氛围缓存（单独的表，也可合并到 movie_classify，但为了兼容旧代码保留）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS atmosphere_cache (
                tmdb_id INTEGER PRIMARY KEY,
                atmosphere TEXT NOT NULL,
                created_at TEXT
            )
        ''')

        # TMDB API 缓存（避免重复请求）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tmdb_cache (
                tmdb_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT
            )
        ''')


# ---------- movie_classify 操作 ----------
def get_cached_classify(tmdb_id):
    """获取电影分类缓存（标签、视觉风格、氛围风格）"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT visual_style, atmosphere_style, tags FROM movie_classify WHERE tmdb_id = ?',
            (tmdb_id,)
        )
        row = cur.fetchone()
        if row:
            return {
                'visual_style': row[0],
                'atmosphere_style': row[1],
                'tags': json.loads(row[2]) if row[2] else []
            }
    return None


def save_classify_to_db(tmdb_id, title, genres, visual_style, atmosphere_style, tags):
    """保存电影分类到缓存"""
    with get_conn() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO movie_classify
            (tmdb_id, title, genres, visual_style, atmosphere_style, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            tmdb_id,
            title,
            genres,
            visual_style,
            atmosphere_style,
            json.dumps(tags, ensure_ascii=False),
            datetime.now().isoformat()
        ))


# ---------- atmosphere_cache 操作 ----------
def get_cached_atmosphere(tmdb_id):
    """获取缓存的氛围风格"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT atmosphere FROM atmosphere_cache WHERE tmdb_id = ?', (tmdb_id,))
        row = cur.fetchone()
        return row[0] if row else None


def save_cached_atmosphere(tmdb_id, atmosphere):
    """保存氛围风格到缓存"""
    with get_conn() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO atmosphere_cache (tmdb_id, atmosphere, created_at)
            VALUES (?, ?, ?)
        ''', (tmdb_id, atmosphere, datetime.now().isoformat()))


# ---------- TMDB 缓存操作 ----------
def get_tmdb_cache(tmdb_id, max_age_days=7):
    """
    获取缓存的 TMDB 数据，如果存在且未过期则返回，否则返回 None
    max_age_days: 缓存有效天数
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT data, created_at FROM tmdb_cache WHERE tmdb_id = ?', (tmdb_id,))
        row = cur.fetchone()
        if row:
            data_json, created_at_str = row
            created_at = datetime.fromisoformat(created_at_str)
            if datetime.now() - created_at < timedelta(days=max_age_days):
                return json.loads(data_json)
    return None


def save_tmdb_cache(tmdb_id, data):
    """保存 TMDB API 数据到缓存"""
    with get_conn() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO tmdb_cache (tmdb_id, data, created_at)
            VALUES (?, ?, ?)
        ''', (tmdb_id, json.dumps(data, ensure_ascii=False), datetime.now().isoformat()))