# services/tmdb.py
"""
TMDB API 服务
所有 TMDB API 调用集中管理
"""
import requests
import pandas as pd
import streamlit as st
from datetime import datetime
from utils.logger import get_logger
from config import (
    TMDB_API_KEY,
    TMDB_IMAGE_BASE,
    TMDB_IMAGE_BASE_W500,
    TMDB_BASE_URL,
    TMDB_CSV_PATH, RATINGS_CSV_PATH
)
from services.cache import CacheTTL
from db.movie_cache import get_tmdb_cache, save_tmdb_cache

logger = get_logger("tmdb")

# ==================== 基础 API 调用 ====================

def get_movie_by_tmdb_id(tmdb_id):
    """直接调用 TMDB API 获取电影详情"""
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=zh-CN"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"获取 TMDB 电影失败 {tmdb_id}: {e}")
        return None


@st.cache_data(ttl=CacheTTL.MEDIUM)
def get_movie_by_tmdb_id_cached(tmdb_id, cache_days=7):
    """
    带缓存的获取 TMDB 电影信息
    先查本地数据库，若无或过期则从 TMDB API 获取并存入缓存
    """
    # 1. 尝试从缓存读取
    cached_data = get_tmdb_cache(tmdb_id)
    if cached_data:
        return cached_data

    # 2. 缓存未命中，调用 API
    data = get_movie_by_tmdb_id(tmdb_id)
    if data:
        save_tmdb_cache(tmdb_id, data)
    return data


@st.cache_data(ttl=CacheTTL.MEDIUM)
def get_tmdb_movie_info(tmdb_id):
    """获取 TMDB 电影信息（中文，用于展示）"""
    if not tmdb_id:
        return None
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=zh-CN"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            genre_names = [g['name'] for g in data.get('genres', [])]
            genres_str = ' · '.join(genre_names) if genre_names else ''
            return {
                'id': data.get('id'),
                'title': data.get('title', ''),
                'genres': genres_str,
                'poster_path': data.get('poster_path'),
                'poster_url': f"{TMDB_IMAGE_BASE}{data.get('poster_path')}" if data.get('poster_path') else None,
                'vote_average': data.get('vote_average', 0),
                'release_date': data.get('release_date', '')[:4],
                'overview': data.get('overview', '')
            }
    except Exception as e:
        logger.error(f"获取电影信息失败: {e}")
    return None


# ==================== 电影列表 API ====================

@st.cache_data(ttl=CacheTTL.SHORT)
def fetch_tmdb_movies(page=1):
    """获取 TMDB 热门电影列表（用于分类页）"""
    url = f"{TMDB_BASE_URL}/movie/popular?api_key={TMDB_API_KEY}&language=zh-CN&page={page}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('results', [])
    except Exception as e:
        logger.error(f"fetch_tmdb_movies 失败: {e}")
    return []


@st.cache_data(ttl=CacheTTL.MEDIUM)
def get_movie_detail(tmdb_id):
    """获取电影详情（用于 categories.py）"""
    if not tmdb_id:
        return None
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=zh-CN"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'id': data.get('id'),
                'title': data.get('title', ''),
                'genres': ' · '.join([g['name'] for g in data.get('genres', [])]),
                'overview': data.get('overview', ''),
                'poster_path': data.get('poster_path'),
                'poster_url': f"{TMDB_IMAGE_BASE}{data.get('poster_path')}" if data.get('poster_path') else None,
                'vote_average': data.get('vote_average', 0),
                'release_date': data.get('release_date', '')[:4],
            }
    except Exception as e:
        logger.error(f"get_movie_detail 失败: {e}")
    return None



@st.cache_data(ttl=CacheTTL.SHORT)
def get_tmdb_hot_movies():
    """从 TMDB 获取当前热门电影（正在热映），并附带详情（获取全球数据，最多60部）"""
    try:
        limit = 120
        all_movies = []
        page = 1
        max_pages = 10
        while len(all_movies) < limit and page <= max_pages:
            url = f"{TMDB_BASE_URL}/movie/now_playing?api_key={TMDB_API_KEY}&language=zh-CN&page={page}"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                movies = data.get('results', [])
                if not movies:
                    break
                all_movies.extend(movies)
                page += 1
            except Exception as e:
                logger.error(f"TMDB 第{page}页请求失败: {e}")
                break

        target_movies = all_movies[:limit]
        enriched = []
        for m in target_movies:
            detail_url = f"{TMDB_BASE_URL}/movie/{m['id']}?api_key={TMDB_API_KEY}&language=zh-CN"
            try:
                detail_resp = requests.get(detail_url, timeout=5)
                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    m['overview'] = detail.get('overview', '')
                    m['genres'] = [g['name'] for g in detail.get('genres', [])]
                else:
                    m['overview'] = ''
                    m['genres'] = []
            except:
                m['overview'] = ''
                m['genres'] = []
            enriched.append(m)

        return enriched

    except Exception as e:
        logger.error(f"TMDB API 调用失败: {e}")
        return []

@st.cache_data(ttl=CacheTTL.SHORT)
def get_tmdb_upcoming_movies():
    """获取即将上映的电影"""
    url = f"{TMDB_BASE_URL}/movie/upcoming?api_key={TMDB_API_KEY}&language=zh-CN&page=1&region=CN"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return data.get('results', [])[:2]
    except:
        return []


@st.cache_data(ttl=CacheTTL.SHORT)
def get_tmdb_hot_movies_simple():
    """获取简单热门电影列表（用于首页热点板块）"""
    url = f"{TMDB_BASE_URL}/movie/now_playing?api_key={TMDB_API_KEY}&language=zh-CN&page=1&region=CN"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return data.get('results', [])
    except:
        return []


@st.cache_data(ttl=CacheTTL.SHORT)
def get_tmdb_now_playing():
    """获取正在热映的电影（用于 hot.py）"""
    url = f"{TMDB_BASE_URL}/movie/now_playing?api_key={TMDB_API_KEY}&language=zh-CN&page=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('results', [])
    except Exception as e:
        logger.error(f"获取正在热映失败: {e}")
        return []


@st.cache_data(ttl=CacheTTL.SHORT)
def get_tmdb_popular():
    """获取热门电影（用于 hot.py）"""
    url = f"{TMDB_BASE_URL}/movie/popular?api_key={TMDB_API_KEY}&language=zh-CN&page=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('results', [])
    except Exception as e:
        logger.error(f"获取热门电影失败: {e}")
        return []


# ==================== 类型映射 ====================

@st.cache_data(ttl=CacheTTL.MEDIUM)
def get_genre_map():
    """从 TMDB 获取类型ID到中文名称的映射"""
    url = f"{TMDB_BASE_URL}/genre/movie/list?api_key={TMDB_API_KEY}&language=zh-CN"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {g['id']: g['name'] for g in data.get('genres', [])}
    except Exception as e:
        logger.error(f"获取类型映射失败: {e}")
        return {}


# ==================== 搜索 ====================

def search_movies_by_title(title):
    """通过标题搜索 TMDB 电影，返回第一条结果"""
    url = f"{TMDB_BASE_URL}/search/movie?api_key={TMDB_API_KEY}&query={title}&language=zh-CN&page=1"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        results = data.get('results', [])
        if results:
            return results[0]
        return None
    except:
        return None


# ==================== 本地 CSV 映射 ====================

@st.cache_data(ttl=CacheTTL.LONG)
def load_tmdb_mapping():
    """从本地 CSV 加载 movieId -> tmdbId 映射"""
    try:
        df = pd.read_csv(TMDB_CSV_PATH)
        if 'tmdbId' not in df.columns:
            logger.error("CSV 文件中没有 tmdbId 列")
            return {}
        return {row['movieId']: row['tmdbId'] for _, row in df.iterrows() if pd.notna(row['tmdbId'])}
    except Exception as e:
        logger.error(f"加载 TMDB 映射失败: {e}")
        return {}


# 全局缓存映射
_TMDB_MAP = None


def get_tmdb_mapping():
    """获取 TMDB 映射（懒加载）"""
    global _TMDB_MAP
    if _TMDB_MAP is None:
        _TMDB_MAP = load_tmdb_mapping()
    return _TMDB_MAP


def get_tmdb_info_by_local_id(local_id):
    """通过本地 movieId 获取 TMDB 信息"""
    tmdb_id = get_tmdb_mapping().get(local_id)
    if not tmdb_id:
        return None
    return get_movie_by_tmdb_id_cached(tmdb_id)


# ==================== TMDB 热门电影（带 AI 评论） ====================

def get_hot_movies(top_k=3):
    """
    从 TMDB 获取当前热门电影（正在热映）
    返回列表，每个元素包含: movieId, title, genres, year, rating, poster_url
    """
    url = f"{TMDB_BASE_URL}/movie/now_playing?api_key={TMDB_API_KEY}&language=zh-CN&page=1&region=CN"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        movies = data.get('results', [])[:top_k]
        if not movies:
            raise ValueError("无数据")

        genre_map = get_genre_map()
        hot_list = []
        for m in movies:
            genre_names = [genre_map.get(gid, '') for gid in m.get('genre_ids', []) if genre_map.get(gid)]
            genres_str = '|'.join(genre_names) if genre_names else "未知"
            release_date = m.get('release_date', '')
            year = int(release_date[:4]) if release_date and len(release_date) >= 4 else 0
            rating = m.get('vote_average', 0.0)
            poster_path = m.get('poster_path')
            poster_url = f"{TMDB_IMAGE_BASE_W500}{poster_path}" if poster_path else None
            hot_list.append({
                'movieId': m['id'],
                'title': m.get('title', ''),
                'genres': genres_str,
                'year': year,
                'rating': rating,
                'poster_url': poster_url
            })
        return hot_list
    except Exception as e:
        logger.error(f"TMDB API 调用失败: {e}")
        return _get_hot_movies_fallback(top_k)


def _get_hot_movies_fallback(top_k=3):
    """备用方案：基于本地评分数据的热门电影"""
    try:
        ratings = pd.read_csv(RATINGS_CSV_PATH)
        movie_counts = ratings['movieId'].value_counts().head(top_k).index
        df = pd.read_csv(TMDB_CSV_PATH)
        hot = df[df['movieId'].isin(movie_counts)][['movieId', 'title', 'genres', 'release_year']].copy()
        avg_ratings = ratings.groupby('movieId')['rating'].mean().to_dict()
        hot['rating'] = hot['movieId'].map(avg_ratings)
        hot = hot.rename(columns={'release_year': 'year'})
        hot['year'] = hot['year'].fillna(0).astype(int)
        hot['rating'] = hot['rating'].fillna(0.0)
        return hot.to_dict('records')
    except Exception as e:
        logger.error(f"本地备用数据也失败: {e}")
        return [
            {"movieId": 1, "title": "样例电影1", "genres": "剧情", "year": 2023, "rating": 8.0, "poster_url": None},
            {"movieId": 2, "title": "样例电影2", "genres": "喜剧", "year": 2023, "rating": 7.5, "poster_url": None},
        ]


# ==================== 电影中文信息（用于浮动聊天等） ====================

@st.cache_data
def get_movie_chinese_info(movie_id):
    """获取电影的中文信息（标题、类型、评分）"""
    df = pd.read_csv(TMDB_CSV_PATH)
    row = df[df['movieId'] == movie_id]
    if row.empty:
        return None
    tmdb_id = row.iloc[0].get('tmdbId')
    if not tmdb_id or pd.isna(tmdb_id):
        return None
    try:
        url = f"{TMDB_BASE_URL}/movie/{int(tmdb_id)}?api_key={TMDB_API_KEY}&language=zh-CN"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            genres = ' · '.join([g['name'] for g in data.get('genres', [])])
            rating_5 = data.get('vote_average', 0) / 2
            return {
                'title': data.get('title', ''),
                'genres': genres,
                'rating': f"{rating_5:.1f}",
                'year': data.get('release_date', '')[:4] if data.get('release_date') else ''
            }
    except Exception as e:
        logger.error(f"获取中文信息失败: {e}")
    return None