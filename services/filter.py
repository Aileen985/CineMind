# services/filter.py
"""
筛选算法 - 统一状态管理 + 扩大候选池
"""
import streamlit as st
import random
from services.llm import call_deepseek
from services.atmosphere import filter_movies_by_atmosphere, filter_movies_by_style
from services.tmdb import fetch_tmdb_movies, get_movie_detail
from services.recommend import get_random_movies_cached
from state import get, set as set_state, StateKeys
from utils.logger import get_logger

logger = get_logger("filter")


def parse_year_range(year_str):
    """将年份范围字符串转为 (start, end) 元组"""
    if not year_str or year_str == "全部":
        return None, None
    if year_str == "经典老片":
        return 0, 1989
    parts = year_str.split('-')
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    return None, None


def apply_filters(movies, genres_filter, year_range, mood_filter=None, style_filter=None):
    """对电影列表应用类型和年代筛选（叠加）"""
    if not movies:
        return []
    filtered = movies
    if genres_filter:
        filtered = [
            m for m in filtered
            if any(g in m.get('genres', '') for g in genres_filter)
        ]
    if year_range and year_range[0] is not None and year_range[1] is not None:
        start, end = year_range
        filtered = [
            m for m in filtered
            if m.get('release_date', '').isdigit() and start <= int(m['release_date']) <= end
        ]
    return filtered[:12]


def _fetch_multiple_pages(pages=5):
    """获取多页热门电影，合并去重，扩大候选池"""
    all_movies = []
    seen_ids = set()
    for page in range(1, pages + 1):
        movies = fetch_tmdb_movies(page=page)
        if not movies:
            continue
        for m in movies:
            mid = m.get('id')
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                all_movies.append(m)
    logger.info(f"从 {pages} 页获取到 {len(all_movies)} 部不重复电影")
    return all_movies


def get_filtered_movies():
    """
    统一入口：优先从 session_state.FILTERED_MOVIES 读取，否则重新计算
    """
    # 如果已有有效结果且非空，直接返回
    if get(StateKeys.IS_FILTERED, False) and get(StateKeys.FILTERED_MOVIES, []):
        movies = get(StateKeys.FILTERED_MOVIES)
        logger.debug(f"使用缓存的筛选结果，共 {len(movies)} 部")
        return movies[:12]

    # 否则重新计算
    selected_moods = get(StateKeys.SELECTED_MOODS, [])
    selected_styles = get(StateKeys.SELECTED_STYLES, [])
    selected_genres = get(StateKeys.SELECTED_GENRES, [])
    selected_year = get(StateKeys.SELECTED_YEAR, "")

    base_movies = []
    logger.info(f"重新计算筛选: moods={selected_moods}, styles={selected_styles}")

    if selected_moods:
        target = selected_moods[0]
        movies = _fetch_multiple_pages(3)   # 扩大候选池
        base_movies = filter_movies_by_atmosphere(movies, target, top_k=12)
        logger.info(f"氛围筛选 '{target}' 得到 {len(base_movies)} 部")
    elif selected_styles:
        target = selected_styles[0]
        movies = _fetch_multiple_pages(3)
        base_movies = filter_movies_by_style(movies, target, top_k=12)
        logger.info(f"视觉风格筛选 '{target}' 得到 {len(base_movies)} 部")
    else:
        # 随机推荐
        random_movies = get(StateKeys.RANDOM_MOVIES, [])
        if not random_movies:
            random_movies = get_random_movies_cached(20) or []
            set_state(StateKeys.RANDOM_MOVIES, random_movies)
        base_movies = random_movies or []
        logger.info(f"随机推荐 {len(base_movies)} 部")

    if not isinstance(base_movies, list):
        base_movies = []

    # 应用类型和年代筛选（叠加）
    year_range = parse_year_range(selected_year)
    if selected_genres or (year_range[0] is not None):
        result = apply_filters(base_movies, selected_genres, year_range)
    else:
        result = base_movies[:12]

    # 存入状态
    set_state(StateKeys.FILTERED_MOVIES, result)
    set_state(StateKeys.IS_FILTERED, True)
    set_state(StateKeys.FILTER_CACHE_VALID, True)   # 标记有效
    logger.info(f"最终筛选结果 {len(result)} 部")
    return result


def refresh_current_filter():
    """
    强制刷新：清除所有相关缓存，重新计算，并确保页面刷新
    """
    logger.info("执行强制刷新")

    # 1. 清除筛选结果状态
    set_state(StateKeys.IS_FILTERED, False)
    set_state(StateKeys.FILTER_CACHE_VALID, False)
    set_state(StateKeys.FILTERED_MOVIES, [])

    # 2. 清除所有可能存在的独立缓存键（mood_*, style_*）
    # 扫描 session_state 中所有以 mood_ 或 style_ 开头的键并删除
    for key in list(st.session_state.keys()):
        if key.startswith("mood_") or key.startswith("style_"):
            del st.session_state[key]
            logger.debug(f"删除缓存键: {key}")

    # 3. 清除随机推荐缓存（让 get_random_movies_cached 重新生成）
    if StateKeys.RANDOM_MOVIES in st.session_state:
        del st.session_state[StateKeys.RANDOM_MOVIES]
        logger.debug("删除随机推荐缓存")

    # 4. 重新计算并存储结果
    try:
        get_filtered_movies()
    except Exception as e:
        logger.error(f"刷新过程中出现异常: {e}")
        st.error("刷新失败，请稍后重试")
        # 至少保证状态是有效的
        set_state(StateKeys.IS_FILTERED, True)
        set_state(StateKeys.FILTERED_MOVIES, [])

    # 5. 强制页面重绘（最重要的一步）
    st.rerun()

def llm_filter_and_reason(candidates, user_query, top_k=12):
    """LLM 筛选并生成推荐理由（口味搜索用）"""
    if not candidates:
        return []
    limited = candidates[:50]
    movies_text = ""
    for i, m in enumerate(limited):
        movies_text += f"{i + 1}. 《{m['title']}》 类型：{m['genres']}\n"

    prompt = f"""用户描述：{user_query}
请从以下候选电影中，选出最符合用户描述的 {top_k} 部电影，并按匹配度从高到低排序。
只输出电影序号，用逗号分隔，例如：3,7,12,19,25。
不要输出其他内容。

候选电影：
{movies_text}
"""
    try:
        result = call_deepseek(prompt, max_tokens=100)
        indices_text = result.strip()
        selected_indices = [int(x.strip()) - 1 for x in indices_text.split(',') if x.strip().isdigit()]
        selected = [limited[i] for i in selected_indices if i < len(limited)]
    except Exception as e:
        logger.error(f"LLM 筛选失败: {e}")
        selected = candidates[:top_k]

    for movie in selected:
        reason_prompt = f"用户需求：{user_query}\n推荐电影《{movie['title']}》，类型：{movie['genres']}\n一句话推荐理由（20字以内）："
        reason = call_deepseek(reason_prompt, max_tokens=50)
        movie['taste_reason'] = reason if reason else "符合你的口味"
    return selected[:top_k]