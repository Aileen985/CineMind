# state.py
"""
统一状态管理
集中管理所有 st.session_state 的键和读写操作
"""
import streamlit as st
from typing import Any, Optional


# ==================== 状态键定义 ====================
class StateKeys:
    """所有 session_state 键的常量定义"""

    # ---------- 用户认证 ----------
    LOGGED_IN = "logged_in"
    USERNAME = "username"

    # ---------- 全局搜索 ----------
    GLOBAL_SEARCH_QUERY = "global_search_query"
    SHOW_SEARCH_UPLOAD = "show_search_upload"
    TAB_SELECTION = "tab_selection"
    CATEGORIES_SEARCH_QUERY = "categories_search_query"

    # ---------- 分类页 ----------
    SELECTED_GENRES = "selected_genres"
    SELECTED_YEAR = "selected_year"
    SELECTED_MOODS = "selected_moods"
    SELECTED_STYLES = "selected_styles"
    CURRENT_PAGE = "current_page"
    FILTERED_MOVIES = "filtered_movies"
    IS_FILTERED = "is_filtered"
    RANDOM_MOVIES = "random_movies"
    SHOW_TASTE = "show_taste"
    TASTE_RESULTS = "taste_results"
    FILTER_CACHE_VALID = "_filter_cache_valid"

    # ---------- 首页 ----------
    SEARCH_RESULTS = "search_results"
    SEARCH_MODE = "search_mode"
    SHOW_IMG_DIALOG = "show_img_dialog"

    # ---------- 热门页 ----------
    CURRENT_PAGE_HOT = "current_page"
    COLD_MOVIES = "cold_movies"
    HOT_TAB_SELECTOR = "hot_tab_selector"

    # ---------- 个性推荐 ----------
    USER_PROFILE_TEXT = "user_profile_text"
    PROFILE_USER = "profile_user"
    PERSONALIZED_RECS = "personalized_recs"
    VISUAL_RECS = "visual_recs"
    DETAIL_MOVIE_ID = "detail_movie_id"
    CURRENT_PAGE_NAME = "current_page"

    # ---------- 浮动聊天 ----------
    USER_ID = "user_id"
    SESSION_ID = "session_id"
    SESSION_START_TIME = "session_start_time"
    SELECTED_MOVIE = "selected_movie"
    FLOAT_MESSAGES = "float_messages"
    FLOAT_CONVERSATION_HISTORY = "float_conversation_history"
    FLOAT_WAITING_TYPE = "float_waiting_type"
    PENDING_ACTION = "_pending_action"

    # ---------- 历史页 ----------
    RATING_PAGE = "rating_page"
    SUMMARY_TEXT = "summary_text"
    SUMMARY_USER = "summary_user"


# ==================== 默认值定义 ====================
DEFAULT_STATE = {
    # 用户认证
    StateKeys.LOGGED_IN: False,
    StateKeys.USERNAME: "",

    # 全局搜索
    StateKeys.GLOBAL_SEARCH_QUERY: "",
    StateKeys.SHOW_SEARCH_UPLOAD: False,
    StateKeys.TAB_SELECTION: "",
    StateKeys.CATEGORIES_SEARCH_QUERY: "",

    # 分类页
    StateKeys.SELECTED_GENRES: [],
    StateKeys.SELECTED_YEAR: "",
    StateKeys.SELECTED_MOODS: [],
    StateKeys.SELECTED_STYLES: [],
    StateKeys.CURRENT_PAGE: 1,
    StateKeys.FILTERED_MOVIES: [],
    StateKeys.IS_FILTERED: False,
    StateKeys.RANDOM_MOVIES: [],
    StateKeys.SHOW_TASTE: False,
    StateKeys.TASTE_RESULTS: [],
    StateKeys.FILTER_CACHE_VALID: False,

    # 首页
    StateKeys.SEARCH_RESULTS: None,
    StateKeys.SEARCH_MODE: None,
    StateKeys.SHOW_IMG_DIALOG: False,

    # 热门页
    StateKeys.COLD_MOVIES: None,
    StateKeys.HOT_TAB_SELECTOR: "🏆 全站热门 (评分人数)",

    # 个性推荐
    StateKeys.USER_PROFILE_TEXT: "",
    StateKeys.PROFILE_USER: "",
    StateKeys.PERSONALIZED_RECS: [],
    StateKeys.VISUAL_RECS: [],
    StateKeys.DETAIL_MOVIE_ID: None,
    StateKeys.CURRENT_PAGE_NAME: "",

    # 浮动聊天
    StateKeys.USER_ID: "default_user",
    StateKeys.SESSION_ID: None,
    StateKeys.SESSION_START_TIME: None,
    StateKeys.SELECTED_MOVIE: None,
    StateKeys.FLOAT_MESSAGES: None,
    StateKeys.FLOAT_CONVERSATION_HISTORY: [],
    StateKeys.FLOAT_WAITING_TYPE: False,
    StateKeys.PENDING_ACTION: None,

    # 历史页
    StateKeys.RATING_PAGE: 1,
    StateKeys.SUMMARY_TEXT: "",
    StateKeys.SUMMARY_USER: "",
}


# ==================== 核心函数 ====================
def init_state():
    """
    初始化所有 session_state 默认值
    在 app.py 启动时调用一次
    """
    for key, default_value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def get(key: str, default: Any = None) -> Any:
    """
    安全获取 session_state 值
    如果键不存在，返回默认值
    """
    return st.session_state.get(key, default)


def set(key: str, value: Any) -> None:
    """
    设置 session_state 值
    """
    st.session_state[key] = value


def has(key: str) -> bool:
    """检查键是否存在"""
    return key in st.session_state


def clear(key: str) -> None:
    """清除指定键的值（设为默认值）"""
    if key in DEFAULT_STATE:
        st.session_state[key] = DEFAULT_STATE[key]
    elif key in st.session_state:
        del st.session_state[key]


def clear_all():
    """清除所有状态（登出时使用）"""
    for key in list(st.session_state.keys()):
        if key in DEFAULT_STATE:
            st.session_state[key] = DEFAULT_STATE[key]
        else:
            del st.session_state[key]


# ==================== 便捷访问器（可选） ====================
# 这些函数提供类型安全的访问，避免字符串拼写错误

# ---------- 用户认证 ----------
def is_logged_in() -> bool:
    return get(StateKeys.LOGGED_IN, False)


def get_username() -> str:
    return get(StateKeys.USERNAME, "")


def set_user(username: str, logged_in: bool = True) -> None:
    set(StateKeys.USERNAME, username)
    set(StateKeys.LOGGED_IN, logged_in)


def logout() -> None:
    set(StateKeys.LOGGED_IN, False)
    set(StateKeys.USERNAME, "")
    set(StateKeys.GLOBAL_SEARCH_QUERY, "")
    # 可选：清除其他敏感状态


# ---------- 全局搜索 ----------
def get_global_search_query() -> str:
    return get(StateKeys.GLOBAL_SEARCH_QUERY, "")


def set_global_search_query(query: str) -> None:
    set(StateKeys.GLOBAL_SEARCH_QUERY, query)


# ---------- 分类页 ----------
def get_selected_genres() -> list:
    return get(StateKeys.SELECTED_GENRES, [])


def get_selected_moods() -> list:
    return get(StateKeys.SELECTED_MOODS, [])


def get_selected_styles() -> list:
    return get(StateKeys.SELECTED_STYLES, [])


def get_selected_year() -> str:
    return get(StateKeys.SELECTED_YEAR, "")


# ---------- 浮动聊天 ----------
def get_float_messages() -> list:
    return get(StateKeys.FLOAT_MESSAGES, [])


def set_float_messages(messages: list) -> None:
    set(StateKeys.FLOAT_MESSAGES, messages)


def add_float_message(message: dict) -> None:
    messages = get_float_messages()
    messages.append(message)
    set_float_messages(messages)