# services/chat.py
"""
聊天服务：会话管理、用户输入处理
"""
import os
import json
import uuid
import sqlite3
from datetime import datetime
import random
from utils.logger import get_logger
from state import get, set as set_state, StateKeys
from db.preferences import get_user_preference_summary, get_user_disliked_movies, save_preference
from db.profiles import get_text_profile
from services.search import text_search
from services.tmdb import get_hot_movies
from services.llm import parse_user_intent, generate_recommendation_response, simple_chat
from config import CHAT_HISTORY_DB

logger = get_logger("chat_service")



# ==================== 数据库初始化 ====================
def init_chat_db():
    os.makedirs(os.path.dirname(CHAT_HISTORY_DB), exist_ok=True)
    conn = sqlite3.connect(CHAT_HISTORY_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            username TEXT NOT NULL,
            session_id TEXT NOT NULL,
            start_time TEXT,
            last_update TEXT,
            messages TEXT,
            PRIMARY KEY (username, session_id)
        )
    ''')
    conn.commit()
    conn.close()


init_chat_db()


# ==================== 会话管理 ====================
def get_latest_user_session(username):
    try:
        conn = sqlite3.connect(CHAT_HISTORY_DB)
        c = conn.cursor()
        c.execute('SELECT session_id FROM sessions WHERE username = ? ORDER BY last_update DESC LIMIT 1', (username,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"获取最新会话失败: {e}")
        return None
    finally:
        conn.close()


def save_chat_history(username, messages, session_id):
    try:
        conn = sqlite3.connect(CHAT_HISTORY_DB)
        c = conn.cursor()
        session_start_time = get(StateKeys.SESSION_START_TIME, datetime.now().isoformat())
        c.execute('''
            INSERT OR REPLACE INTO sessions (username, session_id, start_time, last_update, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            username,
            session_id,
            session_start_time,
            datetime.now().isoformat(),
            json.dumps(messages[-50:], ensure_ascii=False)
        ))
        conn.commit()
        logger.info(f"会话 {session_id} 已保存")
    except Exception as e:
        logger.error(f"保存会话失败: {e}")
    finally:
        conn.close()


def load_chat_history(username, session_id):
    try:
        conn = sqlite3.connect(CHAT_HISTORY_DB)
        c = conn.cursor()
        c.execute('SELECT messages FROM sessions WHERE username = ? AND session_id = ?', (username, session_id))
        row = c.fetchone()
        if row:
            return json.loads(row[0])
    except Exception as e:
        logger.error(f"加载会话失败: {e}")
    finally:
        conn.close()
    return None


# ==================== 电影处理 ====================
def normalize_movie(movie):
    """标准化电影数据结构"""
    if not movie:
        return None
    m = movie.copy()
    if 'movieId' not in m or m['movieId'] is None:
        if 'id' in m and m['id'] is not None:
            m['movieId'] = m['id']
        elif 'tmdbId' in m and m['tmdbId'] is not None:
            m['movieId'] = m['tmdbId']
        else:
            return None
    if 'tmdbId' not in m or m['tmdbId'] is None:
        m['tmdbId'] = m['movieId']
    return m


def get_recommended_ids(float_messages):
    """获取已推荐的电影ID列表"""
    ids = set()
    for msg in float_messages:
        if msg.get("type") == "movie_cards":
            for m in msg.get("data", []):
                mid = m.get('movieId')
                if mid:
                    ids.add(mid)
    return ids


def personalize_and_diversify(movies, username, top_k=3, exclude_ids=None):
    """个性化排序 + 多样性控制"""
    if not movies:
        return []
    if exclude_ids:
        movies = [m for m in movies if m.get('movieId') not in exclude_ids]
    if not movies:
        return []

    user_profile = get_text_profile(username)
    if not user_profile:
        return movies[:top_k]

    user_tags = set(user_profile.get('top_tags', [])[:5])

    scored = []
    for m in movies:
        genres_str = m.get('genres', '')
        if isinstance(genres_str, str):
            genre_list = [g.strip() for g in genres_str.split('|') if g.strip()]
        else:
            genre_list = []
        movie_tags = set(genre_list)

        if user_tags and movie_tags:
            intersection = len(user_tags & movie_tags)
            union = len(user_tags | movie_tags)
            tag_score = intersection / union if union > 0 else 0.0
        else:
            tag_score = 0.0

        explore_score = random.random() * 0.4
        total_score = tag_score * 0.6 + explore_score
        scored.append((m, total_score, genre_list[0] if genre_list else '其他'))

    scored.sort(key=lambda x: x[1], reverse=True)

    genre_groups = {}
    for m, score, genre in scored:
        genre_groups.setdefault(genre, []).append(m)

    diversified = []
    while len(diversified) < top_k and genre_groups:
        for genre in list(genre_groups.keys()):
            if genre_groups[genre]:
                diversified.append(genre_groups[genre].pop(0))
                if len(diversified) >= top_k:
                    break
            else:
                del genre_groups[genre]

    return diversified[:top_k]


def get_hot_movies_filtered(username, top_k=3):
    """获取热门电影并过滤不喜欢"""
    hot = get_hot_movies(top_k * 2)
    disliked = get_user_disliked_movies(username)
    filtered = [m for m in hot if m.get('movieId') not in disliked]
    if len(filtered) < top_k:
        extra = text_search("popular movies", top_k=top_k, username=username)
        existing_ids = [m['movieId'] for m in filtered if m.get('movieId')]
        for m in extra:
            if m.get('movieId') not in existing_ids:
                filtered.append(m)
                if len(filtered) >= top_k:
                    break
    return personalize_and_diversify(filtered, username, top_k)


# ==================== 用户输入处理 ====================
def process_user_input(username, user_input, float_messages):
    """
    处理用户输入，返回更新后的消息列表
    """
    context_more = ["还有吗", "还有没有", "更多", "再来一些", "再来几部", "还有别的吗", "其他的呢", "还有呢", "继续"]
    context_refresh = ["换一批", "换一换", "下一批", "换些别的", "重新推荐", "重新来一批"]
    context_skip = ["不要这部", "不喜欢这部", "跳过", "换一部", "不要第一个", "不要这一部", "跳过这部"]

    is_more_request = any(keyword in user_input for keyword in context_more)
    is_refresh_request = any(keyword in user_input for keyword in context_refresh)
    is_skip_request = any(keyword in user_input for keyword in context_skip)

    conversation_history = get(StateKeys.FLOAT_CONVERSATION_HISTORY, [])

    if is_more_request or is_refresh_request or is_skip_request:
        return _handle_context_request(username, user_input, float_messages,
                                       is_more_request, is_refresh_request, is_skip_request,
                                       conversation_history)
    else:
        return _handle_normal_input(username, user_input, float_messages, conversation_history)


def _handle_context_request(username, user_input, float_messages, is_more, is_refresh, is_skip, conversation_history):
    """处理上下文请求（更多/换一批/跳过）"""
    last_movie_card = None
    for i, msg in enumerate(reversed(float_messages)):
        if msg.get("type") == "movie_cards":
            last_movie_card = msg
            break

    if not last_movie_card:
        float_messages.append({"role": "user", "content": user_input})
        return float_messages, conversation_history

    current_movies = last_movie_card.get("data", [])

    if is_more:
        return _handle_more_request(username, float_messages, conversation_history)
    elif is_refresh:
        return _handle_refresh_request(username, float_messages, conversation_history)
    elif is_skip and current_movies:
        return _handle_skip_request(username, float_messages, conversation_history, current_movies)

    float_messages.append({"role": "user", "content": user_input})
    return float_messages, conversation_history


def _handle_more_request(username, float_messages, conversation_history):
    """处理"更多"请求"""
    recommended_ids = get_recommended_ids(float_messages)
    user_id = get(StateKeys.USER_ID, username)
    more_recs = text_search("popular movies", top_k=12, username=user_id, exclude_ids=list(recommended_ids))
    filtered_recs = [m for m in more_recs if m.get('movieId') not in recommended_ids]
    personalized = personalize_and_diversify(filtered_recs, username, top_k=3, exclude_ids=recommended_ids)
    new_recs = [normalize_movie(m) for m in personalized if normalize_movie(m)]

    if new_recs:
        float_messages.append({"role": "assistant", "type": "movie_cards", "data": new_recs})
        float_messages.append({"role": "assistant", "content": "又找到几部好片，看看有没有你喜欢的？"})
    else:
        float_messages.append({"role": "assistant", "content": "暂时没有更多了，试试换个类型吧～"})

    return float_messages, conversation_history


def _handle_refresh_request(username, float_messages, conversation_history):
    """处理"换一批"请求"""
    recommended_ids = get_recommended_ids(float_messages)
    user_id = get(StateKeys.USER_ID, username)
    new_recs = text_search("popular movies", top_k=12, username=user_id, exclude_ids=list(recommended_ids))
    personalized = personalize_and_diversify(new_recs, username, top_k=3, exclude_ids=recommended_ids)
    norm_recs = [normalize_movie(m) for m in personalized if normalize_movie(m)]

    if norm_recs:
        float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_recs})
        float_messages.append({"role": "assistant", "content": "换一批新鲜好片，看看这些怎么样？"})
    else:
        float_messages.append({"role": "assistant", "content": "暂时没有更多好片了"})

    return float_messages, conversation_history


def _handle_skip_request(username, float_messages, conversation_history, current_movies):
    """处理"跳过"请求"""
    skipped_movie = current_movies[0] if current_movies else None
    if skipped_movie:
        try:
            save_preference(username, skipped_movie.get('movieId'), 'dislike')
            float_messages.append({"role": "assistant",
                                   "content": f"好的，已跳过《{skipped_movie.get('title', '')}》，为你换一部～"})
        except Exception as e:
            logger.error(f"跳过电影失败: {e}")
            float_messages.append({"role": "assistant", "content": "好的，帮你换一部～"})

    recommended_ids = get_recommended_ids(float_messages)
    new_recs = text_search("popular movies", top_k=12, username=username, exclude_ids=list(recommended_ids))
    personalized = personalize_and_diversify(new_recs, username, top_k=3, exclude_ids=recommended_ids)
    norm_recs = [normalize_movie(m) for m in personalized if normalize_movie(m)]

    if norm_recs:
        float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_recs})

    return float_messages, conversation_history


def _handle_normal_input(username, user_input, float_messages, conversation_history):
    """处理普通用户输入（搜索/推荐/聊天）"""
    float_messages.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "user", "content": user_input})
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]

    user_pref = get_user_preference_summary(username)

    # 检查是否在"换个类型"模式
    if get(StateKeys.FLOAT_WAITING_TYPE, False):
        result = _handle_type_request(username, user_input, float_messages, user_pref)
        set_state(StateKeys.FLOAT_WAITING_TYPE, False)
        return result

    # 正常意图解析
    try:
        intent = parse_user_intent(user_input)
    except Exception as e:
        logger.error(f"意图解析失败: {e}")
        intent = {}

    is_chat = all([
        intent.get("genre") is None,
        intent.get("title") is None,
        intent.get("actor") is None,
        "推荐" not in user_input and "找" not in user_input and "看" not in user_input
    ])

    if is_chat and len(user_input) < 15:
        return _handle_chat(user_input, float_messages, conversation_history, user_pref)
    else:
        return _handle_search(username, user_input, float_messages, conversation_history, intent, user_pref)


def _handle_type_request(username, user_input, float_messages, user_pref):
    """处理"换个类型"请求"""
    try:
        intent = parse_user_intent(user_input)
        search_genre = intent.get("genre") or user_input
        recommended_ids = get_recommended_ids(float_messages)
        recs = text_search(search_genre, top_k=12, username=username, exclude_ids=list(recommended_ids))
        personalized = personalize_and_diversify(recs, username, top_k=3, exclude_ids=recommended_ids)
        norm_recs = [normalize_movie(m) for m in personalized if normalize_movie(m)]

        if norm_recs and len(norm_recs) >= 3:
            float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_recs})
            reply = generate_recommendation_response(norm_recs, user_input, intent, user_pref)
            float_messages.append({"role": "assistant", "content": reply})
        else:
            float_messages.append({"role": "assistant", "content": f"没找到「{search_genre}」类型的电影，试试其他类型吧～"})
    except Exception as e:
        logger.error(f"搜索类型失败: {e}")
        float_messages.append({"role": "assistant", "content": "搜索失败，请稍后重试"})

    return float_messages, []


def _handle_chat(user_input, float_messages, conversation_history, user_pref):
    """处理聊天回复"""
    try:
        chat_reply = simple_chat(user_input, conversation_history[:-1], user_pref)
        float_messages.append({"role": "assistant", "content": chat_reply})
        conversation_history.append({"role": "assistant", "content": chat_reply})
    except Exception as e:
        logger.error(f"聊天回复失败: {e}")
        float_messages.append({"role": "assistant", "content": "抱歉，我暂时无法回复，请稍后再试"})
    return float_messages, conversation_history


def _handle_search(username, user_input, float_messages, conversation_history, intent, user_pref):
    """处理搜索/推荐请求"""
    try:
        recommended_ids = get_recommended_ids(float_messages)
        search_query = _build_search_query(user_input, intent)
        recs = text_search(search_query, top_k=12, username=username, exclude_ids=list(recommended_ids))
        personalized = personalize_and_diversify(recs, username, top_k=3, exclude_ids=recommended_ids)
        norm_recs = [normalize_movie(m) for m in personalized if normalize_movie(m)]

        if norm_recs and len(norm_recs) >= 3:
            float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_recs})
            reply = generate_recommendation_response(norm_recs, user_input, intent, user_pref)
            float_messages.append({"role": "assistant", "content": reply})
            conversation_history.append({"role": "assistant", "content": reply})
        else:
            no_result_msg = f"没找到「{search_query}」相关的电影，要不要试试换个说法？"
            float_messages.append({"role": "assistant", "content": no_result_msg})
            conversation_history.append({"role": "assistant", "content": no_result_msg})
    except Exception as e:
        logger.error(f"搜索电影失败: {e}")
        float_messages.append({"role": "assistant", "content": "搜索电影失败，请稍后重试"})

    return float_messages, conversation_history


def _build_search_query(user_input, intent):
    """构建搜索查询"""
    if intent.get("title"):
        return intent["title"]
    elif intent.get("genre"):
        return intent["genre"]
    elif intent.get("actor"):
        return intent["actor"]
    elif intent.get("mood"):
        mood_to_genre = {
            "轻松": "喜剧", "治愈": "剧情", "刺激": "动作",
            "烧脑": "悬疑", "感动": "爱情", "解压": "喜剧"
        }
        return mood_to_genre.get(intent["mood"], user_input)
    else:
        return user_input