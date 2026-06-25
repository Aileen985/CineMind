# services/cache.py
"""
统一缓存管理
"""
import streamlit as st
import hashlib
from config import CACHE_TTL_SHORT, CACHE_TTL_MEDIUM, CACHE_TTL_LONG

# ==================== 缓存配置常量 ====================
class CacheTTL:
    """缓存过期时间（秒）"""
    SHORT = CACHE_TTL_SHORT
    MEDIUM = CACHE_TTL_MEDIUM
    LONG = CACHE_TTL_LONG

# ==================== TMDB 缓存（带本地数据库） ====================
def get_tmdb_cache_key(tmdb_id, language="zh-CN"):
    """生成 TMDB 缓存的键"""
    return f"tmdb_{tmdb_id}_{language}"


def get_tmdb_cached_data(tmdb_id, language="zh-CN"):
    """
    从数据库缓存获取 TMDB 数据
    已迁移到 db.movie_cache.get_tmdb_cache
    """
    from db.movie_cache import get_tmdb_cache
    return get_tmdb_cache(tmdb_id)


def save_tmdb_cached_data(tmdb_id, data, language="zh-CN"):
    """
    保存 TMDB 数据到数据库缓存
    已迁移到 db.movie_cache.save_tmdb_cache
    """
    from db.movie_cache import save_tmdb_cache
    save_tmdb_cache(tmdb_id, data)


# ==================== 电影分类缓存键 ====================
def get_classify_cache_key(tmdb_id):
    """生成电影分类缓存的键"""
    return f"classify_{tmdb_id}"


def get_mood_cache_key(target_mood, page=1):
    """生成氛围筛选缓存的键"""
    return f"mood_{target_mood}_page_{page}"


def get_style_cache_key(target_style, page=1):
    """生成视觉风格筛选缓存的键"""
    return f"style_{target_style}_page_{page}"


def get_random_movies_cache_key(count=20):
    """生成随机电影缓存的键"""
    return f"random_movies_{count}"


# ==================== 用户画像缓存键 ====================
def get_user_profile_cache_key(username):
    """生成用户画像缓存的键"""
    return f"user_profile_{username}"


def get_user_visual_cache_key(username):
    """生成用户视觉画像缓存的键"""
    return f"user_visual_{username}"


# ==================== 通用缓存工具 ====================
def generate_cache_key(*args, **kwargs):
    """
    生成通用缓存键
    基于参数生成一致的哈希值
    """
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def clear_cache_by_prefix(prefix):
    """
    清除所有以指定前缀开头的缓存
    注意：Streamlit 不直接支持前缀清除，这里作为标记
    """
    # 实际使用时，可以配合 st.cache_data.clear() 手动清理
    # 或者使用 st.rerun() 触发缓存重建
    st.cache_data.clear()


# ==================== 建议的缓存装饰器配置 ====================
"""
推荐的 @st.cache_data 配置模板：

@st.cache_data(ttl=CacheTTL.SHORT, show_spinner=False)
def fetch_tmdb_movies(page=1):
    ...

@st.cache_data(ttl=CacheTTL.MEDIUM, show_spinner=False)
def get_movie_detail(tmdb_id):
    ...

@st.cache_data(ttl=CacheTTL.LONG, show_spinner=False)
def get_tmdb_movie_info(tmdb_id):
    ...

@st.cache_resource
def get_clip_model():
    # 模型加载（资源缓存）
    ...
"""