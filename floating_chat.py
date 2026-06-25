# floating_chat.py - 精简版，只负责 UI 渲染
import streamlit as st
import os
import json
import uuid
from datetime import datetime
from functools import wraps
import time

# === 服务层导入 ===
from services.chat import (
    init_chat_db,
    get_latest_user_session,
    save_chat_history,
    load_chat_history,
    normalize_movie,
    personalize_and_diversify,
    get_hot_movies_filtered,
    get_recommended_ids,
    process_user_input,
)
from services.tmdb import get_movie_chinese_info
from services.search import text_search

# === 组件导入 ===
from components import SKELETON_CSS

# === 状态导入 ===
from state import get, set as set_state, StateKeys

# === 其他导入 ===
from movie_detail import show_movie_detail

# === 日志 ===
from utils.logger import get_logger

logger = get_logger("floating_chat")


# ==================== 重试装饰器 ====================
def retry(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"尝试 {attempt + 1}/{max_retries} 失败: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
                    else:
                        logger.error(f"所有重试失败: {e}")
                        raise
            return None
        return wrapper
    return decorator


# ==================== 主函数 ====================

@st.fragment
def show_floating_chat():
    # 骨架屏 CSS
    st.markdown(SKELETON_CSS, unsafe_allow_html=True)

    # --- 状态初始化 ---
    username = get(StateKeys.USERNAME, "default_user")
    set_state(StateKeys.USER_ID, username)

    _init_session(username)
    _init_messages(username)

    if get(StateKeys.FLOAT_CONVERSATION_HISTORY) is None:
        set_state(StateKeys.FLOAT_CONVERSATION_HISTORY, [])
    if get(StateKeys.FLOAT_WAITING_TYPE) is None:
        set_state(StateKeys.FLOAT_WAITING_TYPE, False)

    # --- 处理待处理动作 ---
    pending_action = get(StateKeys.PENDING_ACTION)
    if pending_action is not None:
        set_state(StateKeys.PENDING_ACTION, None)

        if pending_action['type'] == 'user_input':
            user_input = pending_action['data']
            float_messages = get(StateKeys.FLOAT_MESSAGES, [])
            if float_messages and float_messages[-1].get('type') == 'skeleton':
                float_messages.pop()
                set_state(StateKeys.FLOAT_MESSAGES, float_messages)
            _process_user_input(username, user_input)
            st.rerun()
            return

        elif pending_action['type'] == 'refresh':
            float_messages = get(StateKeys.FLOAT_MESSAGES, [])
            if float_messages and float_messages[-1].get('type') == 'skeleton':
                float_messages.pop()
                set_state(StateKeys.FLOAT_MESSAGES, float_messages)
            _handle_refresh_action(username)
            st.rerun()
            return

    # --- 弹出电影详情 ---
    selected_movie = get(StateKeys.SELECTED_MOVIE)
    if selected_movie is not None:
        selected = normalize_movie(selected_movie)
        if selected:
            show_movie_detail(selected)
        else:
            st.error("无法获取有效的电影信息，请重试")
        set_state(StateKeys.SELECTED_MOVIE, None)

    # --- 渲染聊天区域 ---
    _render_chat_messages()

    # --- 底部按钮 ---
    _render_bottom_buttons(username)

    # --- 用户输入 ---
    user_input = st.chat_input("🎬 输入你想看的电影...")
    if user_input:
        float_messages = get(StateKeys.FLOAT_MESSAGES, [])
        float_messages.append({"role": "assistant", "type": "skeleton"})
        set_state(StateKeys.FLOAT_MESSAGES, float_messages)
        set_state(StateKeys.PENDING_ACTION, {'type': 'user_input', 'data': user_input})
        st.rerun()


# ==================== 初始化函数 ====================

def _init_session(username):
    """初始化会话"""
    if get(StateKeys.SESSION_ID) is None:
        latest_session = get_latest_user_session(username)
        if latest_session:
            set_state(StateKeys.SESSION_ID, latest_session)
            logger.info(f"加载已有会话: {latest_session}")
        else:
            session_id = str(uuid.uuid4())[:8]
            set_state(StateKeys.SESSION_ID, session_id)
            set_state(StateKeys.SESSION_START_TIME, datetime.now().isoformat())
            logger.info(f"创建新会话: {session_id}")

    if get(StateKeys.SELECTED_MOVIE) is None:
        set_state(StateKeys.SELECTED_MOVIE, None)


def _init_messages(username):
    """加载或初始化消息"""
    if get(StateKeys.FLOAT_MESSAGES) is None:
        saved_history = load_chat_history(username, get(StateKeys.SESSION_ID))
        if saved_history:
            set_state(StateKeys.FLOAT_MESSAGES, saved_history)
            logger.info(f"加载历史消息: {len(saved_history)} 条")
        else:
            float_messages = [
                {"role": "assistant", "content": "🍿 嗨！我是你的对话式电影推荐官 CineMind。"}
            ]
            hot = get_hot_movies_filtered(username, top_k=3)
            norm_hot = [normalize_movie(m) for m in hot if normalize_movie(m)]
            float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_hot})
            float_messages.append(
                {"role": "assistant",
                 "content": "告诉我你想看什么电影，比如「推荐一部动作片」或者「最近有什么好看的科幻片」～"})
            set_state(StateKeys.FLOAT_MESSAGES, float_messages)


# ==================== 动作处理 ====================

def _process_user_input(username, user_input):
    """处理用户输入（适配 services.chat.process_user_input 的签名）"""
    # 从 session_state 获取当前消息和历史
    float_messages = get(StateKeys.FLOAT_MESSAGES, [])
    conversation_history = get(StateKeys.FLOAT_CONVERSATION_HISTORY, [])

    float_messages, conversation_history = process_user_input(username, user_input, float_messages)

    set_state(StateKeys.FLOAT_MESSAGES, float_messages)
    set_state(StateKeys.FLOAT_CONVERSATION_HISTORY, conversation_history)
    save_chat_history(username, float_messages, get(StateKeys.SESSION_ID))


def _handle_refresh_action(username):
    """处理刷新动作"""
    float_messages = get(StateKeys.FLOAT_MESSAGES, [])
    with st.spinner("正在为你挑选好片..."):
        try:
            recommended_ids = get_recommended_ids(float_messages)
            new_recs = text_search("popular movies", top_k=12, username=username, exclude_ids=list(recommended_ids))
            personalized = personalize_and_diversify(new_recs, username, top_k=3, exclude_ids=recommended_ids)
            norm_recs = [normalize_movie(m) for m in personalized if normalize_movie(m)]

            if norm_recs:
                float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_recs})
                float_messages.append({"role": "assistant", "content": "换一批新鲜好片，看看这些怎么样？"})
                set_state(StateKeys.FLOAT_MESSAGES, float_messages)
                st.toast("已换一批新片！", icon="🔄")
            else:
                float_messages.append({"role": "assistant", "content": "暂时没有找到更多好片，试试其他类型吧～"})
                set_state(StateKeys.FLOAT_MESSAGES, float_messages)
        except Exception as e:
            logger.error(f"换一批失败: {e}")
            float_messages.append({"role": "assistant", "content": "哎呀，出了点小问题，请再试一次～"})
            set_state(StateKeys.FLOAT_MESSAGES, float_messages)

    save_chat_history(username, float_messages, get(StateKeys.SESSION_ID))


# ==================== 渲染函数 ====================

def _render_chat_messages():
    """渲染聊天消息"""
    float_messages = get(StateKeys.FLOAT_MESSAGES, [])
    chat_container = st.container()

    with chat_container:
        for msg_idx, msg in enumerate(float_messages):
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                with st.chat_message("assistant"):
                    if msg.get("type") == "skeleton":
                        _render_skeleton()
                    elif msg.get("type") == "movie_cards":
                        _render_movie_cards(msg["data"], msg_idx)
                    else:
                        st.write(msg["content"])


def _render_skeleton():
    """渲染骨架屏"""
    st.markdown("""
    <div class="skeleton-message">
        <div class="skeleton-text medium"></div>
        <div class="skeleton-text short"></div>
        <div class="skeleton-card">
            <div class="skeleton-card-item"></div>
            <div class="skeleton-card-item"></div>
            <div class="skeleton-card-item"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_movie_cards(movies, msg_idx):
    """渲染电影卡片"""
    if not movies:
        return
    cols = st.columns(3)
    for idx, movie in enumerate(movies[:3]):
        norm_movie = normalize_movie(movie)
        if not norm_movie:
            continue
        with cols[idx]:
            with st.container(border=True):
                _render_movie_poster(norm_movie)
                chinese_info = get_movie_chinese_info(norm_movie['movieId'])
                _render_movie_info(norm_movie, chinese_info, msg_idx, idx)


def _render_movie_poster(norm_movie):
    """渲染电影海报"""
    poster_url = norm_movie.get('poster_url')
    if poster_url and poster_url.startswith('http'):
        st.image(poster_url, use_container_width=True)
    else:
        poster_path = f"D:/coding/CineMind/Feature-engineering/posters/{norm_movie['movieId']}.jpg"
        if os.path.exists(poster_path):
            st.image(poster_path, use_container_width=True)
        else:
            st.markdown(
                f'<div style="background:#2a2f4e; width:100%; aspect-ratio:2/3; display:flex; align-items:center; justify-content:center; color:#666; border-radius:8px;">🎬</div>',
                unsafe_allow_html=True
            )


def _render_movie_info(norm_movie, chinese_info, msg_idx, idx):
    """渲染电影信息"""
    if chinese_info:
        display_title = chinese_info['title']
        display_genres = chinese_info['genres']
        display_rating = chinese_info['rating']
        display_year = chinese_info['year']
    else:
        display_title = norm_movie.get('title', '未知')
        display_genres = norm_movie.get('genres', '').replace('|', ' · ')
        rating_10 = norm_movie.get('rating', 0)
        display_rating = f"{rating_10 / 2:.1f}" if rating_10 else "暂无"
        display_year = norm_movie.get('year', '')

    if st.button(display_title, key=f"title_{norm_movie['movieId']}_{msg_idx}_{idx}", use_container_width=True):
        set_state(StateKeys.SELECTED_MOVIE, norm_movie)
        st.rerun()

    st.caption(display_genres)
    meta_parts = []
    if display_year:
        meta_parts.append(f"📅 {display_year}年")
    meta_parts.append(f"⭐ {display_rating} / 5.0")
    st.caption("  ".join(meta_parts))


def _render_bottom_buttons(username):
    """渲染底部按钮"""
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🔄 换一批", use_container_width=True, key="float_refresh"):
            float_messages = get(StateKeys.FLOAT_MESSAGES, [])
            float_messages.append({"role": "assistant", "type": "skeleton"})
            set_state(StateKeys.FLOAT_MESSAGES, float_messages)
            set_state(StateKeys.PENDING_ACTION, {'type': 'refresh', 'data': None})
            st.rerun()

    with col_b:
        if st.button("🗑️ 重置对话", use_container_width=True, key="float_reset"):
            _reset_conversation(username)
            st.rerun()

    with col_c:
        if st.button("🎭 换个类型", use_container_width=True, key="float_change_type"):
            set_state(StateKeys.FLOAT_WAITING_TYPE, True)
            float_messages = get(StateKeys.FLOAT_MESSAGES, [])
            float_messages.append({"role": "assistant", "content": "你想换成什么类型？(例如：动作、爱情、科幻、喜剧、悬疑)"})
            set_state(StateKeys.FLOAT_MESSAGES, float_messages)
            save_chat_history(username, float_messages, get(StateKeys.SESSION_ID))


def _reset_conversation(username):
    """重置对话"""
    session_id = str(uuid.uuid4())[:8]
    set_state(StateKeys.SESSION_ID, session_id)
    set_state(StateKeys.SESSION_START_TIME, datetime.now().isoformat())

    float_messages = [{"role": "assistant", "content": "🍿 嗨！我是你的对话式电影推荐官 CineMind。"}]
    hot = get_hot_movies_filtered(username, top_k=3)
    norm_hot = [normalize_movie(m) for m in hot if normalize_movie(m)]
    float_messages.append({"role": "assistant", "type": "movie_cards", "data": norm_hot})
    float_messages.append({"role": "assistant", "content": "告诉我你想看什么电影，比如「推荐一部动作片」～"})

    set_state(StateKeys.FLOAT_MESSAGES, float_messages)
    set_state(StateKeys.FLOAT_CONVERSATION_HISTORY, [])
    set_state(StateKeys.FLOAT_WAITING_TYPE, False)

    save_chat_history(username, float_messages, session_id)
    st.toast("对话已重置", icon="🗑️")