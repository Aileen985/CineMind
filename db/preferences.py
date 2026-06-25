# db/preferences.py
import sqlite3
import time
from config import RATING_DB_PATH

def get_conn():
    """获取与评分数据库的连接"""
    return sqlite3.connect(RATING_DB_PATH, timeout=10)

def init_table():
    """创建 preferences 表（如果不存在）"""
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS preferences (
                username TEXT NOT NULL,
                tmdbId INTEGER NOT NULL,
                preference TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                PRIMARY KEY (username, tmdbId)
            )
        ''')

def save_preference(username, tmdb_id, preference):
    """
    保存用户对某部电影的偏好。
    如果 preference 为 None，则删除该记录（取消喜欢/不喜欢）。
    preference 应为 'like' 或 'dislike'。
    """
    with get_conn() as conn:
        if preference is None:
            conn.execute(
                'DELETE FROM preferences WHERE username = ? AND tmdbId = ?',
                (username, tmdb_id)
            )
        else:
            timestamp = int(time.time())
            conn.execute('''
                INSERT OR REPLACE INTO preferences (username, tmdbId, preference, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (username, tmdb_id, preference, timestamp))
    return True

def get_my_preference(username, tmdb_id):
    """获取用户对某部电影的偏好（'like' 或 'dislike' 或 None）"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT preference FROM preferences WHERE username = ? AND tmdbId = ?',
            (username, tmdb_id)
        )
        row = cur.fetchone()
        return row[0] if row else None

def get_user_liked_movies(username):
    """获取用户所有喜欢（'like'）的电影 tmdb_id 列表"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT tmdbId FROM preferences WHERE username = ? AND preference = "like"',
            (username,)
        )
        return [row[0] for row in cur.fetchall()]

def get_user_disliked_movies(username):
    """获取用户所有不喜欢（'dislike'）的电影 tmdb_id 列表"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT tmdbId FROM preferences WHERE username = ? AND preference = "dislike"',
            (username,)
        )
        return [row[0] for row in cur.fetchall()]

def get_user_preference_summary(username):
    """
    获取用户偏好的文本摘要（用于对话推荐）。
    返回字符串，如 "用户喜欢 3 部电影，不喜欢 2 部。"
    """
    liked = get_user_liked_movies(username)
    disliked = get_user_disliked_movies(username)
    if not liked and not disliked:
        return "新用户，暂无偏好记录。"
    parts = []
    if liked:
        parts.append(f"用户喜欢 {len(liked)} 部电影")
    if disliked:
        parts.append(f"不太喜欢 {len(disliked)} 部")
    return "，".join(parts) + "。"