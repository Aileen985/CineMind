# services/llm.py
"""
LLM 服务：统一管理所有 DeepSeek API 调用
包含：
- 通用 LLM 调用（call_llm / call_deepseek）
- 意图解析（parse_user_intent）
- 推荐语生成（generate_recommendation_response）
- 简单对话（simple_chat）
"""
import os
import hashlib
import json
import sqlite3
from datetime import datetime
from openai import OpenAI
from utils.logger import get_logger
from config import DEEPSEEK_API_KEY
import pandas as pd
from collections import Counter
from services.models import get_tmdb_df
from db.ratings import get_user_ratings

logger = get_logger("llm")

# ==================== DeepSeek 客户端 ====================
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# ==================== 缓存数据库 ====================
from config import DATA_DIR
os.makedirs(DATA_DIR, exist_ok=True)
CACHE_DB_PATH = os.path.join(DATA_DIR, "recommendation_cache.db")

def init_cache_db():
    """初始化推荐语缓存数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS recommendation_cache (
            cache_key TEXT PRIMARY KEY,
            movie_ids TEXT,
            user_input TEXT,
            user_pref TEXT,
            reply TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info(f"✅ 缓存数据库已就绪: {CACHE_DB_PATH}")


# 初始化缓存数据库
init_cache_db()

# ============================================
# 1. 通用 LLM 调用
# ============================================

def call_llm(prompt, max_tokens=100, temperature=0.3):
    """
    通用 DeepSeek API 调用
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"thinking": {"type": "disabled"}}
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return None


def call_deepseek(prompt, max_tokens=100, temperature=0.3):
    """call_llm 的别名（兼容旧代码）"""
    return call_llm(prompt, max_tokens, temperature)


# ============================================
# 2. 意图解析（对话式推荐专用）
# ============================================

def parse_user_intent(user_input: str) -> dict:
    """
    让大模型理解用户想看什么电影
    返回: {"genre": "Action", "mood": "轻松", "actor": "成龙", "year": "2024", "title": "片名"}
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {
                    "role": "system",
                    "content": """你是一个电影推荐助手的意图理解模块。

电影类型必须使用以下**英文值**（不要用中文）：
Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Mystery, Romance, Science Fiction, Thriller, War, Western, TV Movie

分析用户输入，返回 JSON，genre 字段必须从上面选择：
{"genre": "英文类型或null", "mood": "情绪或null", "actor": "演员名或null", "year": "年代或null", "title": "片名或null"}

示例1：用户说"浪漫的爱情剧" → {"genre": "Romance", "mood": "浪漫", "actor": null, "year": null, "title": null}
示例2：用户说"我想看科幻片" → {"genre": "Science Fiction", "mood": null, "actor": null, "year": null, "title": null}
示例3：用户说"成龙的电影" → {"genre": null, "mood": null, "actor": "成龙", "year": null, "title": null}

只返回 JSON，不要有其他文字。"""
                },
                {"role": "user", "content": user_input}
            ],
            temperature=0.1
        )
        result = response.choices[0].message.content
        result = result.replace("```json", "").replace("```", "").strip()
        return json.loads(result)
    except Exception as e:
        logger.error(f"意图解析失败: {e}")
        return {"genre": None, "mood": None, "actor": None, "year": None, "title": None}


# ============================================
# 3. 推荐语生成（带缓存）
# ============================================

def get_cache_key(movie_ids, user_input, user_pref):
    """生成缓存键"""
    ids_str = ','.join(sorted([str(mid) for mid in movie_ids]))
    key_str = f"{ids_str}|{user_input[:50]}|{user_pref[:100]}"
    return hashlib.md5(key_str.encode()).hexdigest()


def get_cached_recommendation(movie_ids, user_input, user_pref):
    """从缓存获取推荐语"""
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    cache_key = get_cache_key(movie_ids, user_input, user_pref)
    c.execute('SELECT reply, created_at FROM recommendation_cache WHERE cache_key = ?', (cache_key,))
    row = c.fetchone()
    conn.close()

    if row:
        reply, created_at = row
        try:
            created_time = datetime.fromisoformat(created_at)
            if (datetime.now() - created_time).total_seconds() < 86400:  # 24小时缓存
                logger.info(f"✅ 使用缓存 (key: {cache_key[:8]}...)")
                return reply
        except:
            pass
    return None


def save_cached_recommendation(movie_ids, user_input, user_pref, reply):
    """保存推荐语到缓存"""
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    cache_key = get_cache_key(movie_ids, user_input, user_pref)
    c.execute('''
        INSERT OR REPLACE INTO recommendation_cache (cache_key, movie_ids, user_input, user_pref, reply, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (cache_key, ','.join(map(str, movie_ids)), user_input[:200], user_pref[:200], reply,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"💾 已缓存 (key: {cache_key[:8]}...)")


def generate_recommendation_response(movies, user_input, intent, user_pref=""):
    """生成推荐语（带缓存）"""
    if not movies:
        return "哎呀，没找到符合你要求的电影。能再说具体一点吗？"

    # 提取电影ID列表（用于缓存键）
    movie_ids = [m.get('movieId') for m in movies[:3] if m.get('movieId')]
    if not movie_ids:
        movie_ids = [0, 0, 0]

    # 先检查缓存
    cached_reply = get_cached_recommendation(movie_ids, user_input, user_pref)
    if cached_reply:
        return cached_reply

    # 构建提示词
    movie_titles = [m.get('title', '') for m in movies[:3]]
    movie_info = []
    for m in movies[:3]:
        info = f"{m.get('title', '')}"
        if m.get('genres'):
            info += f" ({m.get('genres', '').replace('|', '、')})"
        movie_info.append(info)

    intent_info = ""
    if intent and intent.get("genre"):
        intent_info += f"用户想看{intent['genre']}类型"
    if intent and intent.get("mood"):
        intent_info += f"，心情是{intent['mood']}"

    prompt = f"""{user_pref}
{intent_info}
用户说："{user_input}"
推荐的电影：{', '.join(movie_info)}

请生成一句自然、友好的推荐语（20-30字），说明推荐理由，要体现出对用户喜好的考虑。"""

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": "你是 CineMind，一个热情、专业的电影推荐官。回复要简短亲切，2-3句话。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100
        )
        reply = response.choices[0].message.content.strip()

        # 保存到缓存
        save_cached_recommendation(movie_ids, user_input, user_pref, reply)
        return reply
    except Exception as e:
        logger.error(f"生成推荐语失败: {e}")
        return f"为你推荐《{movie_titles[0]}》和另外几部好片，看看有没有感兴趣的？"


# ============================================
# 4. 简单对话
# ============================================

def simple_chat(user_input: str, conversation_history: list = None, user_pref: str = "") -> str:
    """简单对话"""
    messages = [
        {
            "role": "system",
            "content": f"你是 CineMind，一个电影推荐助手。{user_pref}回答要简短友好，不要超过两句话。"
        }
    ]

    if conversation_history:
        messages.extend(conversation_history[-4:])

    messages.append({"role": "user", "content": user_input})

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"对话失败: {e}")
        return "不好意思，我现在有点卡顿。你能再说一遍吗？"


# ============================================
# 5. 其他常用 LLM 函数
# ============================================

def get_movie_ai_comment(movie_title):
    """使用 DeepSeek 生成电影 AI 解读（15字以内）"""
    prompt = f"为电影《{movie_title}》生成一句简短的热门解读（15字以内），突出特点。不要输出电影标题。"
    return call_llm(prompt, max_tokens=30) or "精彩推荐"


def get_or_generate_reason(tmdb_id, title, user_query):
    """获取或生成推荐理由"""
    reason_prompt = f"用户需求：{user_query}\n推荐电影《{title}》的理由（20字以内）："
    reason = call_llm(reason_prompt, max_tokens=50)
    return reason if reason else "值得一看"


def get_long_term_preferences(username):
    """从评分和反馈中提取用户长期偏好（类型、导演、演员）"""
    ratings = get_user_ratings(username)
    if not ratings:
        return "新用户，暂无长期偏好。"

    high_movie_ids = [mid for mid, rat, ts in ratings if rat >= 4]
    if not high_movie_ids:
        high_movie_ids = [mid for mid, rat, ts in ratings]
    tmdb = get_tmdb_df()
    high_movies = tmdb[tmdb['movieId'].isin(high_movie_ids)]

    genre_counter = Counter()
    director_counter = Counter()
    actor_counter = Counter()
    for _, row in high_movies.iterrows():
        genres = str(row['genres']).split('|')
        genre_counter.update(genres)
        if pd.notna(row['director']):
            director_counter[row['director']] += 1
        if pd.notna(row['actors']):
            actors = [a.strip() for a in row['actors'].split(',')[:2]]
            actor_counter.update(actors)

    top_genres = [g for g, _ in genre_counter.most_common(3)] if genre_counter else []
    top_directors = [d for d, _ in director_counter.most_common(2)] if director_counter else []
    top_actors = [a for a, _ in actor_counter.most_common(2)] if actor_counter else []

    pref_str = f"用户最喜欢类型：{', '.join(top_genres) if top_genres else '未知'}。"
    if top_directors:
        pref_str += f" 偏爱导演：{', '.join(top_directors)}。"
    if top_actors:
        pref_str += f" 关注演员：{', '.join(top_actors)}。"
    return pref_str

def generate_llm_summary(prompt, max_tokens=200, temperature=0.7):
    """生成 LLM 总结"""
    return call_llm(prompt, max_tokens=max_tokens, temperature=temperature)