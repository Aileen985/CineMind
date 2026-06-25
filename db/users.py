import sqlite3
import hashlib
from config import USER_DB_PATH

def get_conn():
    return sqlite3.connect(USER_DB_PATH)

def init_table():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT 1 FROM users WHERE username = ?', (username,))
            if cur.fetchone():
                return False, '用户名已存在'
            cur.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                        (username, hash_password(password)))
            return True, '注册成功'
    except sqlite3.Error as e:
        return False, f'注册失败: {e}'

def login_user(username, password):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id, password FROM users WHERE username = ?', (username,))
            row = cur.fetchone()
            if not row:
                return False, '用户名不存在', None
            if row[1] != hash_password(password):
                return False, '密码错误', None
            return True, '登录成功', {'id': row[0]}
    except sqlite3.Error as e:
        return False, f'登录失败: {e}', None