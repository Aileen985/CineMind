# services/hot.py
"""
热度算法
"""
import random
from datetime import datetime, timedelta
import sqlite3
import requests
from services.llm import call_llm
from db.pools import get_cold_pool
from config import TMDB_API_KEY, TMDB_IMAGE_BASE, HOT_MOVIES_SNAPSHOTS
from utils.logger import get_logger

logger = get_logger("hot")


# ================== TMDB 数据获取 ==================
def get_tmdb_now_playing():
    """获取正在热映的电影"""
    url = f"https://api.themoviedb.org/3/movie/now_playing?api_key={TMDB_API_KEY}&language=zh-CN&page=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('results', [])
    except Exception as e:
        logger.error(f"获取正在热映失败: {e}")
        return []


def get_tmdb_popular():
    """获取热门电影"""
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=zh-CN&page=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('results', [])
    except Exception as e:
        logger.error(f"获取热门电影失败: {e}")
        return []


def get_genre_map():
    """获取类型映射"""
    url = f"https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB_API_KEY}&language=zh-CN"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return {g['id']: g['name'] for g in data.get('genres', [])}
    except Exception as e:
        logger.error(f"获取类型映射失败: {e}")
        return {}


# ================== 增长率计算 ==================
def get_growth_rate(current_pop, old_pop):
    """计算增长率"""
    if old_pop and old_pop > 0:
        return ((current_pop - old_pop) / old_pop) * 100
    return None


def get_simulated_growth_rate(popularity, vote_count):
    """模拟增长率（无历史数据时使用）"""
    seed = int(popularity * 10) + vote_count
    random.seed(seed)
    growth = 5 + (popularity % 55)
    random.seed()
    return round(growth, 1)


def calculate_hot_index(movies):
    """计算全局热度指数（加权平均）"""
    if not movies:
        return 0.0
    weighted_sum = 0
    total_votes = 0
    for m in movies[:20]:
        pop = m.get('popularity', 0)
        votes = m.get('vote_count', 0)
        weighted_sum += pop * votes
        total_votes += votes
    return round(weighted_sum / total_votes, 1) if total_votes > 0 else 0.0


# ================== 批量生成评论 ==================
def batch_generate_hot_comments(movies):
    """批量生成热门电影解读"""
    if not movies:
        return {}
    movie_text = "\n".join([f"{i+1}. 《{m.get('title', '未知')}》" for i, m in enumerate(movies)])
    prompt = f"""以下是一些热门电影，请为每部电影生成一句简短的热门解读（15字以内），突出特点。
按顺序输出，用分号隔开，不要编号。

电影列表：
{movie_text}
解读："""
    try:
        result = call_llm(prompt, max_tokens=300)
        comments = [r.strip() for r in result.split('；') if r.strip()]
        while len(comments) < len(movies):
            comments.append("热门推荐")
        return {movies[i].get('id', i): comments[i] for i in range(len(movies))}
    except:
        return {m.get('id', i): "热门推荐" for i, m in enumerate(movies)}


def batch_generate_cold_comments(movies):
    """批量生成冷门电影推荐理由"""
    if not movies:
        return {}
    movie_text = "\n".join([f"{i+1}. 《{m.get('title', '未知')}》" for i, m in enumerate(movies)])
    prompt = f"""以下是一些冷门电影，请为每部电影生成一句吸引人的推荐理由（20字以内），突出其亮点。
按顺序输出，用分号隔开，不要编号。

电影列表：
{movie_text}
推荐理由："""
    try:
        result = call_llm(prompt, max_tokens=200)
        reasons = [r.strip() for r in result.split('；') if r.strip()]
        while len(reasons) < len(movies):
            reasons.append("冷门佳作")
        return {movies[i].get('tmdb_id', i): reasons[i] for i in range(len(movies))}
    except:
        return {m.get('tmdb_id', i): "冷门佳作" for i, m in enumerate(movies)}


def get_cold_movies_with_comments(limit=6):
    """获取带评论的冷门电影"""
    cold_movies = get_cold_pool(limit=limit)
    if not cold_movies:
        return []
    comments = batch_generate_cold_comments(cold_movies)
    for movie in cold_movies:
        movie['ai_comment'] = comments.get(movie.get('tmdb_id'), "冷门佳作")
    return cold_movies


# ================== 快照数据库操作 ==================
TODAY = datetime.now().strftime('%Y-%m-%d')


def init_snapshot_db():
    """初始化快照数据库"""
    import os
    if os.path.exists(HOT_MOVIES_SNAPSHOTS):
        conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_snapshots'")
        if c.fetchone():
            c.execute("PRAGMA table_info(movie_snapshots)")
            columns = [col[1] for col in c.fetchall()]
            if 'movie_id' in columns:
                conn.close()
                os.remove(HOT_MOVIES_SNAPSHOTS)
                print("已删除旧数据库，将创建新表")
            else:
                conn.close()
        else:
            conn.close()

    conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS movie_snapshots (
            tmdb_id INTEGER,
            title TEXT,
            snapshot_date TEXT,
            popularity REAL,
            vote_count INTEGER,
            vote_average REAL,
            PRIMARY KEY (tmdb_id, snapshot_date)
        )
    ''')
    conn.commit()
    conn.close()


def has_todays_snapshot():
    """检查今天是否已经保存过快照"""
    conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
    c = conn.cursor()
    c.execute('SELECT 1 FROM movie_snapshots WHERE snapshot_date = ? LIMIT 1', (TODAY,))
    result = c.fetchone()
    conn.close()
    return result is not None


def save_snapshot_if_needed(movies):
    """仅当今天还没有快照时才保存"""
    if not movies:
        return
    if has_todays_snapshot():
        return
    conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
    c = conn.cursor()
    for m in movies:
        c.execute('''
            INSERT OR REPLACE INTO movie_snapshots 
            (tmdb_id, title, snapshot_date, popularity, vote_count, vote_average)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (m.get('id'), m.get('title'), TODAY,
              m.get('popularity', 0), m.get('vote_count', 0), m.get('vote_average', 0)))
    conn.commit()
    conn.close()


def get_snapshot_growth_rate(tmdb_id, days=7):
    """从快照获取增长率"""
    conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
    c = conn.cursor()
    past = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    c.execute('SELECT popularity FROM movie_snapshots WHERE tmdb_id = ? AND snapshot_date = ?', (tmdb_id, past))
    old = c.fetchone()
    c.execute('SELECT popularity FROM movie_snapshots WHERE tmdb_id = ? AND snapshot_date = ?', (tmdb_id, TODAY))
    current = c.fetchone()
    conn.close()
    if old and current and old[0] > 0:
        return ((current[0] - old[0]) / old[0]) * 100
    return None


def has_historical_data():
    """检查是否有历史数据（7天前）"""
    conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute('SELECT 1 FROM movie_snapshots WHERE snapshot_date <= ? LIMIT 1', (cutoff,))
    result = c.fetchone()
    conn.close()
    return result is not None


def cleanup_old_snapshots(days=30):
    """清理旧快照"""
    conn = sqlite3.connect(HOT_MOVIES_SNAPSHOTS)
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    c.execute('DELETE FROM movie_snapshots WHERE snapshot_date < ?', (cutoff,))
    conn.commit()
    conn.close()