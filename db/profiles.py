# db/profiles.py
import sqlite3
import json
import numpy as np
from config import PROFILE_DB_PATH

def get_conn():
    return sqlite3.connect(PROFILE_DB_PATH, timeout=10)

def init_table():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_text_profile (
                username TEXT PRIMARY KEY,
                top_tags TEXT,
                top_atm_style TEXT,
                top_vis_style TEXT,
                avg_rating REAL,
                total_count INTEGER,
                updated_at TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_visual_profile (
                username TEXT PRIMARY KEY,
                visual_embedding TEXT,
                updated_at TEXT
            )
        ''')

def save_text_profile(username, top_tags, top_atm_style, top_vis_style, avg_rating, total_count):
    with get_conn() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO user_text_profile
            (username, top_tags, top_atm_style, top_vis_style, avg_rating, total_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            username,
            json.dumps(top_tags, ensure_ascii=False),
            top_atm_style,
            top_vis_style,
            round(avg_rating, 2) if avg_rating else 0,
            total_count or 0
        ))

def get_text_profile(username):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT top_tags, top_atm_style, top_vis_style, avg_rating, total_count FROM user_text_profile WHERE username = ?', (username,))
        row = cur.fetchone()
        if row:
            return {
                'top_tags': json.loads(row[0]) if row[0] else [],
                'top_atm_style': row[1],
                'top_vis_style': row[2],
                'avg_rating': row[3],
                'total_count': row[4]
            }
    return None

def save_visual_profile(username, visual_embedding):
    if isinstance(visual_embedding, np.ndarray):
        embedding_list = visual_embedding.tolist()
    else:
        embedding_list = visual_embedding
    with get_conn() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO user_visual_profile
            (username, visual_embedding, updated_at)
            VALUES (?, ?, datetime('now'))
        ''', (username, json.dumps(embedding_list)))

def get_visual_profile(username):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT visual_embedding FROM user_visual_profile WHERE username = ?', (username,))
        row = cur.fetchone()
        if row and row[0]:
            return np.array(json.loads(row[0]))
    return None