# pages/categories.py - 精简版，只负责 UI
import streamlit as st
import random

# === 服务层导入 ===
from services.tmdb import fetch_tmdb_movies, get_movie_detail
from services.atmosphere import (
    filter_movies_by_atmosphere,
    filter_movies_by_style,
    get_or_analyze_atmosphere,
    get_or_analyze_visual,
)
from services.filter import (
    get_filtered_movies,
    refresh_current_filter,
    llm_filter_and_reason,
    parse_year_range,
)
from services.search import multi_modal_search
from services.llm import get_or_generate_reason
from services.recommend import get_random_movies_cached

# === 组件导入 ===
from components import NO_POSTER_URL, format_stars

# === 状态导入 ===
from state import get, set as set_state, StateKeys

# === 其他导入 ===
from movie_detail import show_movie_detail
from utils.logger import get_logger

logger = get_logger("categories")


# ==================== 主函数 ====================

def show():
    # 处理点击卡片跳转电影详情
    if st.query_params.get('detail_id'):
        detail_id = st.query_params.get('detail_id')
        movie_detail = get_movie_detail(detail_id)
        if movie_detail:
            movie_for_detail = {
                'tmdbId': detail_id,
                'title': movie_detail.get('title'),
                'overview': movie_detail.get('overview', ''),
                'genres': movie_detail.get('genres', ''),
                'year': movie_detail.get('release_date', ''),
                'rating': movie_detail.get('vote_average', 0) / 2,
                'poster_url': movie_detail.get('poster_url')
            }
            show_movie_detail(movie_for_detail)
        st.query_params.clear()

    # --- 样式 ---
    _render_styles()

    # --- 页面标题 ---
    st.markdown('<p class="page-title"><i class="fas fa-lightbulb">光影百态 · 随心甄选</p>', unsafe_allow_html=True)
    st.markdown('<p style="color:#98a1c3; margin-bottom: 1.5rem;">甄选多样观影风格，匹配专属观影品味</p>', unsafe_allow_html=True)
    st.markdown('<div class="category-page">', unsafe_allow_html=True)
    st.markdown('<div style="border-top: 1px solid #252838; margin: 16px 0;"></div>', unsafe_allow_html=True)

    # --- 当前筛选条件展示 ---
    _render_filter_tags()

    # --- 左侧筛选栏 + 右侧内容 ---
    left_col, right_col = st.columns([1.1, 3])

    with left_col:
        _render_filter_sidebar()

    with right_col:
        _render_content()


# ==================== 样式 ====================

def _render_styles():
    st.markdown("""
    <style>
    .category-page .stButton button {
        border-radius: 40px !important;
        border: none !important;
        padding: 6px 12px !important;
        font-size: 0.75rem !important;
        font-weight: 400 !important;
    }
    .category-page .stButton button[data-kind="secondary"] {
        background: #1a1e2c !important;
        color: #bfc3dd !important;
        border: 1px solid #252838 !important;
    }
    .category-page .stButton button[data-kind="secondary"]:hover {
        background: #2a2e44 !important;
        color: white !important;
    }
    .category-page .stButton button[data-kind="primary"] {
        background: #7c4dff !important;
        color: white !important;
    }
    .filter-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: #c084fc;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .filter-tag {
        background: #7c3aed30;
        padding: 4px 12px;
        border-radius: 40px;
        font-size: 0.7rem;
        display: inline-block;
        margin-right: 6px;
        color: #c4b5fd;
    }
    .movie-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 20px;
    }
    .movie-card {
        background: #11131f;
        border-radius: 16px;
        border: 1px solid #252838;
        overflow: hidden;
        transition: all 0.3s;
        cursor: pointer;
        height: 100%;
        display: flex;
        flex-direction: column;
    }
    .movie-card:hover {
        transform: translateY(-4px);
        border-color: #7c4dff;
    }
    .movie-poster {
        width: 100%;
        aspect-ratio: 2 / 3;
        object-fit: cover;
        background: #1a1e2c;
    }
    .movie-info {
        padding: 12px;
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    .movie-title {
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        cursor: pointer;
    }
    .movie-title:hover {
        color: #7c4dff;
    }
    .movie-genre {
        font-size: 0.7rem;
        color: #98a1c3;
        margin-bottom: 8px;
    }
    .movie-reason {
        background: #1a1e2c;
        padding: 6px 8px;
        border-radius: 8px;
        font-size: 0.65rem;
        color: #c4b5fd;
        margin-top: 4px;
    }
    @media (max-width: 1200px) { .movie-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 900px) { .movie-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 600px) { .movie-grid { grid-template-columns: 1fr; } }
    div[class*="st-key-"] .stButton > button {
        background: #1a1e2c;
        border: 1px solid #252838;
        color: #bfc3dd;
        border-radius: 40px;
        padding: 6px 12px;
        font-size: 0.75rem;
    }
    div[class*="st-key-"] .stButton > button:hover {
        background: #2a2e44;
        color: white;
    }
    div[class*="st-key-"] .stButton > button[kind="primary"],
    div[class*="st-key-"] .stButton > button[data-kind="primary"] {
        background: #7c4dff !important;
        color: white !important;
        border-color: #7c4dff !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ==================== 筛选条件标签 ====================

def _render_filter_tags():
    selected_genres = get(StateKeys.SELECTED_GENRES, [])
    selected_year = get(StateKeys.SELECTED_YEAR, "")
    selected_moods = get(StateKeys.SELECTED_MOODS, [])
    selected_styles = get(StateKeys.SELECTED_STYLES, [])

    filters = []
    if selected_genres:
        filters.append(f"类型: {', '.join(selected_genres)}")
    if selected_year:
        filters.append(f"年代: {selected_year}")
    if selected_moods:
        filters.append(f"氛围: {selected_moods[0]}")
    if selected_styles:
        filters.append(f"视觉风格: {selected_styles[0]}")

    if filters:
        st.markdown(
            '<div style="margin-bottom: 12px;">' +
            ' '.join([f'<span class="filter-tag">{f}</span>' for f in filters]) +
            '</div>',
            unsafe_allow_html=True
        )


# ==================== 左侧筛选栏 ====================

def _render_filter_sidebar():
    # --- 类型筛选 ---
    st.markdown('<div class="filter-title"><i class="fas fa-theater-masks"></i> 类型</div>', unsafe_allow_html=True)
    selected_genres = get(StateKeys.SELECTED_GENRES, [])
    genre_list = ["全部", "动作", "喜剧", "爱情", "悬疑", "恐怖", "动画", "科幻", "纪录片"]

    for i in range(0, len(genre_list), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(genre_list):
                g = genre_list[i + j]
                is_active = (g == "全部" and len(selected_genres) == 0) or (g in selected_genres)
                with col:
                    if st.button(g, key=f"genre_{g}", use_container_width=True,
                                 type="primary" if is_active else "secondary"):
                        if g == "全部":
                            set_state(StateKeys.SELECTED_GENRES, [])
                        else:
                            if g in selected_genres:
                                selected_genres.remove(g)
                            else:
                                selected_genres.append(g)
                            set_state(StateKeys.SELECTED_GENRES, selected_genres)
                        set_state(StateKeys.FILTER_CACHE_VALID, False)
                        st.rerun()

    st.markdown('<div style="border-top: 1px solid #252838; margin: 16px 0;"></div>', unsafe_allow_html=True)

    # --- 年代筛选 ---
    st.markdown('<div class="filter-title"><i class="fas fa-calendar-alt"></i> 年代</div>', unsafe_allow_html=True)
    selected_year = get(StateKeys.SELECTED_YEAR, "")
    year_list = ["全部", "2020-2026", "2010-2019", "2000-2009", "1990-1999", "经典老片"]

    for i in range(0, len(year_list), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j < len(year_list):
                y = year_list[i + j]
                is_active = (y == "全部" and selected_year == "") or (selected_year == y)
                with col:
                    if st.button(y, key=f"year_{y}", use_container_width=True,
                                 type="primary" if is_active else "secondary"):
                        if y == "全部":
                            set_state(StateKeys.SELECTED_YEAR, "")
                        else:
                            set_state(StateKeys.SELECTED_YEAR, y)
                        set_state(StateKeys.FILTER_CACHE_VALID, False)
                        st.rerun()

    st.markdown('<div style="border-top: 1px solid #252838; margin: 16px 0;"></div>', unsafe_allow_html=True)

    # --- 氛围筛选 ---
    st.markdown('<div class="filter-title"><i class="fas fa-heart"></i> 观影氛围</div>', unsafe_allow_html=True)
    selected_moods = get(StateKeys.SELECTED_MOODS, [])
    mood_list = ["全部", "奇幻穹宇", "热血史诗", "烟火人间", "暗影谜踪", "怅然回望", "荒诞冷眼"]

    for i in range(0, len(mood_list), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j < len(mood_list):
                m = mood_list[i + j]
                is_active = (m == "全部" and len(selected_moods) == 0) or (m in selected_moods)
                with col:
                    if st.button(m, key=f"mood_{m}", use_container_width=True,
                                 type="primary" if is_active else "secondary"):
                        if m == "全部":
                            set_state(StateKeys.SELECTED_MOODS, [])
                        else:
                            if m in selected_moods:
                                selected_moods.remove(m)
                            else:
                                selected_moods.append(m)
                            set_state(StateKeys.SELECTED_MOODS, selected_moods)
                            set_state(StateKeys.FILTER_CACHE_VALID, False)
                            refresh_current_filter()
                        st.rerun()

    st.markdown('<div style="border-top: 1px solid #252838; margin: 16px 0;"></div>', unsafe_allow_html=True)

    # --- 画面风格筛选 ---
    st.markdown('<div class="filter-title"><i class="fas fa-palette"></i> 画面风格</div>', unsafe_allow_html=True)
    selected_styles = get(StateKeys.SELECTED_STYLES, [])
    style_list = ["全部", "复古影调", "日常质感", "清冷静谧", "柔光梦镜", "风格显影"]

    for i in range(0, len(style_list), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j < len(style_list):
                s = style_list[i + j]
                is_active = (s == "全部" and len(selected_styles) == 0) or (s in selected_styles)
                with col:
                    if st.button(s, key=f"style_{s}", use_container_width=True,
                                 type="primary" if is_active else "secondary"):
                        if s == "全部":
                            set_state(StateKeys.SELECTED_STYLES, [])
                        else:
                            if s in selected_styles:
                                selected_styles.remove(s)
                            else:
                                selected_styles.append(s)
                            set_state(StateKeys.SELECTED_STYLES, selected_styles)
                            set_state(StateKeys.FILTER_CACHE_VALID, False)
                            refresh_current_filter()
                        st.rerun()

    st.markdown('<div style="border-top: 1px solid #252838; margin: 16px 0;"></div>', unsafe_allow_html=True)


# ==================== 右侧内容区 ====================

def _render_content():
    col_search, col_btn = st.columns([4, 1])
    with col_search:
        search_query = st.text_input("搜索电影", placeholder="🔍 搜索电影标题或输入口味描述...",
                                     label_visibility="collapsed", key="local_search",
                                     autocomplete="off")
    with col_btn:
        taste_trigger = st.button("按口味排序", use_container_width=True, key="taste_sort_btn")

    # --- 按口味排序 ---
    if taste_trigger and search_query:
        with st.spinner("AI 正在理解你的口味并检索..."):
            candidates = multi_modal_search(
                query_text=search_query,
                image_path=None,
                mode="text",
                top_k=50
            )
            if candidates:
                final_recs = llm_filter_and_reason(candidates, search_query, top_k=12)
                filtered_recs = []
                for rec in final_recs:
                    tmdb_id = rec.get('tmdbId') or rec.get('movieId')
                    if tmdb_id:
                        detail = get_movie_detail(tmdb_id)
                        if detail and detail.get('vote_average', 0) >= 3:
                            rec['taste_reason'] = rec.get('taste_reason', '符合你的口味')
                            filtered_recs.append(rec)
                    else:
                        filtered_recs.append(rec)
                set_state(StateKeys.TASTE_RESULTS, filtered_recs)
                set_state(StateKeys.SHOW_TASTE, True)
            else:
                st.warning("未找到相关电影")
            st.rerun()

    # --- 口味推荐结果 ---
    show_taste = get(StateKeys.SHOW_TASTE, False)
    taste_results = get(StateKeys.TASTE_RESULTS, [])

    if show_taste and taste_results:
        _render_taste_results(taste_results)
    else:
        _render_filtered_movies()


# ==================== 口味推荐结果 ====================

def _render_taste_results(taste_results):
    st.markdown("### 🎯 按口味推荐结果")
    taste_movies = taste_results[:12]

    for i in range(0, len(taste_movies), 4):
        cols = st.columns(4)
        for j, col in enumerate(cols):
            if i + j < len(taste_movies):
                movie = taste_movies[i + j]
                tmdb_info = get_movie_detail(movie.get('tmdbId') or movie.get('movieId'))
                if tmdb_info:
                    title = tmdb_info['title']
                    genres = tmdb_info['genres']
                    poster_url = tmdb_info['poster_url']
                    vote_10 = tmdb_info.get('vote_average', 0)
                    vote_5 = round(vote_10 / 2, 1)
                    stars = format_stars(vote_5)
                    movie_id = tmdb_info['id']
                else:
                    title = movie['title']
                    genres = movie['genres'].replace('|', ' · ')
                    poster_url = None
                    vote_5 = 0
                    stars = ""
                    movie_id = movie.get('tmdbId') or movie.get('movieId')

                poster_html = f'<img class="movie-poster" src="{poster_url if poster_url else NO_POSTER_URL}" onerror="this.src=\'{NO_POSTER_URL}\'">' if poster_url else f'<div class="movie-poster" style="display:flex;align-items:center;justify-content:center;">🎬</div>'

                with col:
                    st.markdown(f"""
                    <div class="movie-card" onclick="window.location.href='?detail_id={movie_id}'" style="cursor:pointer;">
                        {poster_html}
                        <div class="movie-info">
                            <div class="movie-title">{title}</div>
                            <div class="movie-genre">{genres}</div>
                            <div class="movie-reason"> {stars} {vote_5}</div>
                            <div class="movie-reason" style="margin-top: 6px;">💡 {movie.get('taste_reason', '推荐')[:50]}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    if st.button("清除口味推荐，返回分类筛选"):
        set_state(StateKeys.SHOW_TASTE, False)
        set_state(StateKeys.TASTE_RESULTS, [])
        st.rerun()
    st.markdown("---")


# ==================== 筛选结果 ====================

def _render_filtered_movies():
    display_movies = get_filtered_movies()

    selected_moods = get(StateKeys.SELECTED_MOODS, [])
    selected_styles = get(StateKeys.SELECTED_STYLES, [])
    selected_genres = get(StateKeys.SELECTED_GENRES, [])
    selected_year = get(StateKeys.SELECTED_YEAR, "")

    if display_movies:
        if selected_moods:
            st.markdown(f"#### 🎨 {selected_moods[0]} 氛围影片")
        elif selected_styles:
            st.markdown(f"#### 🎨 {selected_styles[0]} 视觉风格影片")
        elif selected_genres or selected_year:
            st.markdown("#### 🎯 筛选结果")
        else:
            st.markdown("#### 🎲 随机推荐")

        for i in range(0, len(display_movies), 4):
            cols = st.columns(4)
            for j, col in enumerate(cols):
                if i + j < len(display_movies):
                    movie = display_movies[i + j]
                    poster_url = movie.get('poster_url')
                    vote_10 = movie.get('vote_average', 0)
                    vote_5 = round(vote_10 / 2, 1)
                    stars = format_stars(vote_5)
                    movie_id = movie.get('id')
                    reason = movie.get('reason', '推荐')

                    poster_html = f'<img class="movie-poster" src="{poster_url if poster_url else NO_POSTER_URL}" onerror="this.src=\'{NO_POSTER_URL}\'">' if poster_url else f'<div class="movie-poster" style="display:flex;align-items:center;justify-content:center;">🎬</div>'

                    with col:
                        st.markdown(f"""
                        <div class="movie-card" onclick="window.location.href='?detail_id={movie_id}'" style="cursor:pointer;">
                            {poster_html}
                            <div class="movie-info">
                                <div class="movie-title">{movie.get('title', '未知')}</div>
                                <div class="movie-genre">{movie.get('genres', '')}</div>
                                <div class="movie-reason"> {stars} {vote_5}</div>
                                <div class="movie-reason" style="margin-top: 6px;">💡 {reason[:50]}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.info("没有找到符合条件的电影")

    if st.button("🔄 刷新推荐", key="refresh_category", use_container_width=True):
        refresh_current_filter()
        st.rerun()


if __name__ == "__main__":
    show()