# pages/home.py
import streamlit as st
import os
import tempfile
import requests
from datetime import datetime

# === 服务层导入 ===
from services.tmdb import (
    get_tmdb_hot_movies,
    get_tmdb_upcoming_movies,
    get_tmdb_hot_movies_simple,
    get_tmdb_info_by_local_id,
    get_movie_by_tmdb_id_cached,
)
from services.models import get_tmdb_df
from services.search import image_search, hybrid_recommendation, text_search
from services.atmosphere import filter_movies_by_atmosphere, get_or_analyze_atmosphere_with_cache
from services.llm import get_movie_ai_comment, call_llm
from services.cache import CacheTTL

# === 数据库导入 ===
from db.ratings import get_user_ratings

# === 组件导入 ===
from components import NO_POSTER_URL, star_html, render_movie_card

# === 状态导入 ===
from state import get, StateKeys

# === 日志 ===
from utils.logger import get_logger

from config import TMDB_API_KEY, TMDB_IMAGE_BASE

logger = get_logger("home")


# ==================== 主函数 ====================

def show():
    st.set_page_config(page_title="CineMind · 首页", layout="wide")

    username = get(StateKeys.USERNAME, 'guest')
    if username == 'guest':
        st.warning("请先登录")
        st.stop()

    # 页面标题
    st.markdown('<p class="page-title">光影识心，智荐佳片</p>', unsafe_allow_html=True)
    st.markdown(
        '<p style="color:#98a1c3; margin-bottom: 1.5rem;">依托多模态AI技术，每一部推荐都有据可循</p>',
        unsafe_allow_html=True
    )

    # 卡片样式
    _render_styles()

    # --- Tab 导航 ---
    tab_rec, tab_sci, tab_love, tab_mystery, tab_style = st.tabs(
        ["✨ 专属影汇", "🌌 奇幻穹宇", "💔 怅然回望", "🧠 暗影迷踪", "🎞️ 寻影同调"]
    )

    # --- Tab 1: 专属影汇 ---
    with tab_rec:
        _render_personalized_movies(username)

    # --- Tab 2: 奇幻穹宇 ---
    with tab_sci:
        _render_atmosphere_movies(username, "奇幻穹宇", "奔赴星河幻境，邂逅整片天穹浪漫")

    # --- Tab 3: 怅然回望 ---
    with tab_love:
        _render_atmosphere_movies(username, "怅然回望", "遍历各样故事，回望心底万千感触")

    # --- Tab 4: 暗影谜踪 ---
    with tab_mystery:
        _render_atmosphere_movies(username, "暗影谜踪", "穿行暗影迷局，探索迷雾之下的真相")

    # --- Tab 5: 寻影同调 ---
    with tab_style:
        _render_style_search(username)

    # --- 本周热门电影 ---
    _render_hot_movies()

    # --- 评分历史 ---
    _render_rating_history(username)

    st.markdown("---")


# ==================== 样式 ====================

def _render_styles():
    st.markdown("""
    <style>
    .stImage img {
        width: 100%;
        height: 280px !important;
        object-fit: cover;
        border-radius: 12px;
    }
    .movie-title {
        min-height: 50px;
        font-weight: bold;
        margin-top: 8px;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
    }
    .movie-card-content {
        display: flex;
        flex-direction: column;
        height: 100%;
    }
    .movie-reason {
        margin-top: auto;
    }
    div[data-testid="column"] > div {
        height: 100%;
    }
    .hot-movie-box { background-color: #11131f; border-radius: 24px; padding: 18px; margin-bottom: 12px; }
    .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .trend-badge { background-color: #181c28; color: #e5e7eb; padding: 4px 12px; border-radius: 30px; font-size: 0.85rem; }
    .rank-item { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .rank-num { font-size: 2rem; }
    .ai-tag { color: #c084fc; margin-left: 8px; font-size: 0.9rem; }
    .tag { background-color: #252a3a; padding: 6px 12px; border-radius: 30px; margin-right: 8px; margin-bottom: 8px; display: inline-block; }
    div[data-testid="stVerticalBlock"]:has(> div > div > div[data-testid="stTabs"]) .stTabs [data-baseweb="tab"] {
        background: #181c28 !important;
        padding: 8px 20px !important;
        border-radius: 40px !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        display: inline-block;
        cursor: pointer;
        color: white !important;
        border: none !important;
        margin: 0 4px !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div > div > div[data-testid="stTabs"]) .stTabs [aria-selected="true"] {
        background: #7c4dff !important;
        color: white !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div > div > div[data-testid="stTabs"]) .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div > div > div[data-testid="stTabs"]) .stTabs div[role="tablist"] {
        border-bottom: none !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ==================== 专属影汇 ====================

def _render_personalized_movies(username):
    st.caption("依托观影偏好，智能生成你的个性化影片合集")
    from pages.personal import get_personalized_movies

    movies = get_personalized_movies(username, top_k=6)
    if movies:
        cols = st.columns(6)
        for idx, movie in enumerate(movies):
            with cols[idx]:
                card_movie = {
                    'title': movie.get('title', ''),
                    'poster_url': movie.get('poster_url'),
                    'genres': movie.get('genres_ch', '').split(' · ') if movie.get('genres_ch') else [],
                    'vote_average': movie.get('rating_ch', 0) * 2,
                    'reason': movie.get('reason', '根据你的观影偏好推荐')
                }
                render_movie_card(card_movie, f"rec_{movie.get('tmdb_id')}_{idx}", height=420)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("📋 查看完整片单", key="view_full_personalized", use_container_width=True):
                st.toast("请点击顶部导航栏的「个性推荐」标签页查看完整片单", icon="ℹ️")
    else:
        st.info("暂无推荐，请先去个性推荐页面刷新推荐或评分")


# ==================== 氛围筛选 ====================

def _render_atmosphere_movies(username, target_atmosphere, caption):
    st.caption(caption)
    hot_movies = get_tmdb_hot_movies()
    filtered = filter_movies_by_atmosphere(hot_movies, target_atmosphere, top_k=12)

    if filtered:
        for movie in filtered:
            if 'reason' not in movie:
                reason_prompt = f"推荐{target_atmosphere}电影《{movie.get('title', '')}》的理由（20字以内）："
                reason = call_llm(reason_prompt, max_tokens=50)
                movie['reason'] = reason if reason else f"{target_atmosphere}佳作"

        for row in range(0, len(filtered[:12]), 6):
            cols = st.columns(6)
            for idx, movie in enumerate(filtered[row:row + 6]):
                with cols[idx]:
                    render_movie_card(movie, f"atm_{target_atmosphere}_{row}_{idx}", height=480)
    else:
        st.info(f"暂无符合条件的{target_atmosphere}影片")


# ==================== 寻影同调 ====================

def _render_style_search(username):
    st.caption("依托多模态AI技术，每一次影片匹配都有据可循")
    mode = st.radio("选择功能模式", ["同调匹配", "影片溯源"], horizontal=True)

    if mode == "影片溯源":
        _render_trace_mode(username)
    else:
        _render_mood_mode(username)


def _render_trace_mode(username):
    st.info("上传海报或截图，精准识别画面对应的电影")
    uploaded_img = st.file_uploader("上传海报/截图", type=["png", "jpg", "jpeg"], key="trace_img")

    if uploaded_img and st.button("🔍 溯源", key="trace_btn"):
        with st.spinner("正在识别中..."):
            temp_path = os.path.join(tempfile.gettempdir(), f"trace_{username}_{int(datetime.now().timestamp())}.jpg")
            with open(temp_path, "wb") as f:
                f.write(uploaded_img.getbuffer())
            results = image_search(temp_path, top_k=6)
            os.remove(temp_path)

            if results:
                st.subheader("🔍 识别结果")
                for movie in results[:6]:
                    if 'reason' not in movie:
                        reason_prompt = f"推荐电影《{movie['title']}》的理由（20字以内）："
                        reason = call_llm(reason_prompt, max_tokens=50)
                        movie['reason'] = reason if reason else "值得一看"

                cols = st.columns(6)
                for idx, movie in enumerate(results[:6]):
                    with cols[idx]:
                        tmdb_info = get_tmdb_info_by_local_id(movie['movieId'])
                        if not tmdb_info:
                            st.warning(f"无法获取《{movie['title']}》的中文信息")
                            continue
                        card_movie = {
                            'title': tmdb_info.get('title'),
                            'poster_path': tmdb_info.get('poster_path'),
                            'vote_average': tmdb_info.get('vote_average', 0),
                            'genres': [g['name'] for g in tmdb_info.get('genres', [])],
                            'reason': movie.get('reason', '值得一看')
                        }
                        render_movie_card(card_movie, f"trace_{idx}", height=480)
            else:
                st.warning("未找到匹配的电影")


def _render_mood_mode(username):
    st.info("描述观影氛围，或上传海报，AI为你推荐同质感影片")
    text_input = st.text_area("氛围描述", placeholder="例如：清冷文艺、复古胶片、治愈温情", key="mood_text")
    uploaded_img = st.file_uploader("上传海报/截图（可选）", type=["png", "jpg", "jpeg"], key="mood_img")

    if st.button("🎯 同调推荐", key="mood_btn"):
        if not text_input and not uploaded_img:
            st.warning("请至少输入氛围描述或上传一张图片")
        else:
            with st.spinner("AI 正在分析并匹配..."):
                temp_path = None
                if uploaded_img:
                    temp_path = os.path.join(tempfile.gettempdir(), f"mood_{username}_{int(datetime.now().timestamp())}.jpg")
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_img.getbuffer())

                results = hybrid_recommendation(temp_path, top_k=12) if uploaded_img else text_search(text_input, top_k=12)

                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

                if results:
                    st.subheader("✨ 推荐影片")
                    for movie in results[:12]:
                        if 'reason' not in movie:
                            reason_prompt = f"推荐电影《{movie['title']}》的理由（20字以内）："
                            reason = call_llm(reason_prompt, max_tokens=50)
                            movie['reason'] = reason if reason else "值得一看"

                    for row in range(0, len(results[:12]), 6):
                        cols = st.columns(6)
                        for idx, movie in enumerate(results[row:row + 6]):
                            with cols[idx]:
                                tmdb_info = get_tmdb_info_by_local_id(movie['movieId'])
                                if not tmdb_info:
                                    st.warning(f"无法获取《{movie['title']}》的中文信息")
                                    continue
                                card_movie = {
                                    'title': tmdb_info.get('title'),
                                    'poster_path': tmdb_info.get('poster_path'),
                                    'vote_average': tmdb_info.get('vote_average', 0),
                                    'genres': [g['name'] for g in tmdb_info.get('genres', [])],
                                    'reason': movie.get('reason', '值得一看')
                                }
                                render_movie_card(card_movie, f"mood_{idx}_{row}", height=480)
                else:
                    st.warning("未找到相关电影")


# ==================== 本周热门电影 ====================

def _render_hot_movies():
    st.markdown("""
    <style>
    .hot-movie-box { background-color: #11131f; border-radius: 24px; padding: 18px; margin-bottom: 12px; }
    .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .trend-badge { background-color: #181c28; color: #e5e7eb; padding: 4px 12px; border-radius: 30px; font-size: 0.85rem; }
    .rank-item { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .rank-num { font-size: 2rem; }
    .ai-tag { color: #c084fc; margin-left: 8px; font-size: 0.9rem; }
    .tag { background-color: #252a3a; padding: 6px 12px; border-radius: 30px; margin-right: 8px; margin-bottom: 8px; display: inline-block; }
    </style>
    """, unsafe_allow_html=True)

    hot_movies_simple = get_tmdb_hot_movies_simple()
    trailer_movies = get_tmdb_upcoming_movies()

    col_title_left, col_title_right = st.columns([3, 1])
    with col_title_left:
        st.markdown("### <i class='fas fa-fire' style='color:#ff6b6b;'></i> 本周热门电影 · 趋势解读", unsafe_allow_html=True)
    with col_title_right:
        st.markdown('<div class="trend-badge"><i class="fas fa-chart-line"></i> 社区热度+AI解读</div>', unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="hot-movie-box">', unsafe_allow_html=True)
        if hot_movies_simple:
            medals = ["🥇", "🥈", "🥉"]
            for idx, movie in enumerate(hot_movies_simple[:3]):
                title = movie.get('title', '未知影片')
                ai_comment = get_movie_ai_comment(title)
                st.markdown(f"""
                <div class="rank-item">
                    <div class="rank-num">{medals[idx]}</div>
                    <div>
                        <strong>{title}</strong>
                        <span class="ai-tag">AI解读：{ai_comment}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="hot-movie-box">', unsafe_allow_html=True)
        st.markdown('<i class="fas fa-video"></i> <strong>🔥 预告片精选 & AI微评</strong>', unsafe_allow_html=True)
        if trailer_movies:
            tags_html = '<div style="margin-top:12px;">'
            for movie in trailer_movies:
                title = movie.get('title', '未知影片')
                ai_comment = get_movie_ai_comment(title)
                tags_html += f'<span class="tag"><i class="fab fa-youtube"></i> {title} · AI: {ai_comment}</span>'
            tags_html += '</div>'
            st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


# ==================== 评分历史 ====================

def _render_rating_history(username):
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.markdown("### <i class='fas fa-chart-simple'></i> 你的评分历史 · 偏好洞察", unsafe_allow_html=True)
    with col_h2:
        st.markdown('<div class="trend-badge">最近评分</div>', unsafe_allow_html=True)

    user_ratings = get_user_ratings(username)
    if user_ratings and len(user_ratings) > 0:
        recent_movies = []
        for movie_id, rating, timestamp in user_ratings[:6]:
            tmdb_data = get_movie_by_tmdb_id_cached(movie_id)
            if tmdb_data:
                title = tmdb_data.get('title', f'电影 ID: {movie_id}')
                genres = [g['name'] for g in tmdb_data.get('genres', [])]
                genre = genres[0] if genres else '电影'
            else:
                title = f'电影 ID: {movie_id}'
                genre = '电影'
            date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            recent_movies.append({
                'title': title,
                'rating': rating,
                'date': date_str,
                'genre': genre
            })

        if recent_movies:
            cols = st.columns(6)
            for idx, movie in enumerate(recent_movies[:6]):
                with cols[idx]:
                    with st.container(border=True, height=160):
                        full = int(movie['rating'])
                        half = movie['rating'] - full >= 0.5
                        empty = 5 - full - (1 if half else 0)
                        stars = "★" * full + ("½" if half else "") + "☆" * empty
                        st.markdown(f"""
                        <div>
                            <div style="font-weight:bold; min-height:40px;">{movie['title']}</div>
                            <div><i class="fas fa-star" style="color:#fbbf24;"></i> {movie['rating']}</div>
                            <div style="font-size:0.7rem;">{movie['date']}</div>
                            <div class="ai-reason">{movie['genre']}</div>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.info("暂无评分记录，去首页给电影评分吧～")
    else:
        st.info("暂无评分记录，去首页给电影评分吧～")


if __name__ == "__main__":
    show()