# pages/personal.py - 精简版，只负责 UI
import streamlit as st
import os
from dotenv import load_dotenv

# === 算法导入（从 services 层） ===
from services.recommend import (
    get_personalized_recommendations,
    get_visual_recommendations,
    get_cold_recommendations,
    generate_batch_reasons,
)
from services.tmdb import get_tmdb_movie_info

# === 数据库导入 ===
from db.ratings import get_user_ratings as get_ratings_from_db
from db.profiles import get_text_profile
from db.ratings import get_user_stats

# === 组件导入 ===
from components import NO_POSTER_URL, format_stars, convert_to_5_star

# === 状态导入 ===
from state import get, set as set_state, StateKeys

# === 日志 ===
from utils.logger import get_logger

load_dotenv()
logger = get_logger("personal")


# ==================== 主页面 ====================

def show():
    # 处理电影详情跳转
    if st.query_params.get('detail_id'):
        set_state(StateKeys.DETAIL_MOVIE_ID, st.query_params.get('detail_id'))
        set_state(StateKeys.CURRENT_PAGE_NAME, "movie_detail")
        st.query_params.clear()
        st.rerun()

    # --- CSS 样式 ---
    _render_styles()

    # --- 获取用户 ---
    username = get(StateKeys.USERNAME, 'guest')
    if username == 'guest':
        st.warning("请先登录")
        st.stop()

    st.markdown('<p class="page-title">✨ 专属影汇</p>', unsafe_allow_html=True)
    st.markdown(
        '<p style="color:#98a1c3; margin-bottom: 1.5rem;">以观影足迹为影，邂逅独属于你的影片</p>',
        unsafe_allow_html=True
    )

    # --- 用户画像 ---
    _build_user_profile(username)

    # --- 主推荐 ---
    _render_recommendations(username)


# ==================== 样式 ====================

def _render_styles():
    st.markdown("""
    <style>
    .profile-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: rgba(18, 22, 40, 0.6);
        backdrop-filter: blur(8px);
        border-radius: 28px;
        padding: 12px 24px;
        margin: 20px 0;
        border: 1px solid rgba(139,92,246,0.3);
        gap: 16px;
    }
    .llm-profile {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 0.85rem;
        color: #c4b5fd;
    }
    .refresh-btn {
        background: #7c3aed;
        border: none;
        padding: 8px 20px;
        border-radius: 40px;
        color: white;
        font-weight: 500;
        cursor: pointer;
    }
    .rec-card {
        background: #11131f;
        border-radius: 16px;
        border: 1px solid #252838;
        overflow: hidden;
        transition: all 0.3s;
        height: 100%;
        cursor: pointer;
    }
    .rec-card:hover {
        transform: translateY(-4px);
        border-color: #7c4dff;
    }
    .rec-poster {
        width: 100%;
        aspect-ratio: 2 / 3;
        object-fit: cover;
        background: #1a1e2c;
    }
    .rec-info {
        padding: 12px;
    }
    .rec-title {
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        cursor: pointer;
    }
    .rec-title:hover {
        color: #7c4dff;
    }
    .rec-genre {
        font-size: 0.7rem;
        color: #98a1c3;
        margin-bottom: 8px;
    }
    .rec-reason {
        background: #1a1e2c;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 0.65rem;
        color: #c4b5fd;
        margin-top: 8px;
    }
    .rec-rating {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 0.7rem;
        color: #fbbf24;
    }
    </style>
    """, unsafe_allow_html=True)


# ==================== 用户画像 ====================

def _build_user_profile(username):
    """构建用户画像展示"""
    user_profile_text = get(StateKeys.USER_PROFILE_TEXT)
    profile_user = get(StateKeys.PROFILE_USER)

    if not user_profile_text or profile_user != username:
        profile = get_text_profile(username)
        if profile and profile.get('total_count', 0) > 0:
            top_tags = profile.get('top_tags', [])
            top_atm = profile.get('top_atm_style', '')
            top_vis = profile.get('top_vis_style', '')

            if not top_tags:
                ratings_data = get_ratings_from_db(username)
                genre_counts = {}
                for tmdb_id, rating, timestamp in ratings_data:
                    movie_info = get_tmdb_movie_info(tmdb_id)
                    if movie_info and movie_info.get('genres'):
                        for g in movie_info['genres'].split(' · '):
                            genre_counts[g] = genre_counts.get(g, 0) + 1
                sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
                top_tags = [g for g, _ in sorted_genres[:3]]

            profile_text = f"喜欢 {', '.join(top_tags[:3])}" if top_tags else "暂无明确偏好"
            if top_atm:
                profile_text += f"，偏爱 {top_atm} 氛围"
            if top_vis:
                profile_text += f"，视觉风格倾向 {top_vis}"
            set_state(StateKeys.USER_PROFILE_TEXT, profile_text)
        else:
            set_state(StateKeys.USER_PROFILE_TEXT, "新用户，暂无评分数据")
        set_state(StateKeys.PROFILE_USER, username)

    st.markdown(f"""
    <div class="profile-row">
        <div class="llm-profile">
            <span>🎬 用户画像：{get(StateKeys.USER_PROFILE_TEXT)}</span>
        </div>
        <button class="refresh-btn" onclick="location.href='?refresh=true'">🔄 刷新推荐</button>
    </div>
    """, unsafe_allow_html=True)

    if st.query_params.get('refresh') == 'true':
        set_state(StateKeys.PERSONALIZED_RECS, [])
        set_state(StateKeys.VISUAL_RECS, [])
        st.query_params.clear()
        st.rerun()


# ==================== 推荐渲染 ====================

def _render_recommendations(username):
    """渲染所有推荐板块"""

    # --- 1. 个性化推荐 ---
    if get(StateKeys.PERSONALIZED_RECS) is None:
        set_state(StateKeys.PERSONALIZED_RECS, [])

    if not get(StateKeys.PERSONALIZED_RECS):
        with st.spinner("正在为你生成个性化推荐..."):
            enriched = _fetch_and_enrich_recommendations(username, top_k=12)
            if enriched:
                reasons = generate_batch_reasons(enriched, get(StateKeys.USER_PROFILE_TEXT), "推荐")
                for i, movie in enumerate(enriched):
                    movie['reason'] = reasons[i] if i < len(reasons) else "值得一看"
            set_state(StateKeys.PERSONALIZED_RECS, enriched)

    recs = get(StateKeys.PERSONALIZED_RECS)

    if recs:
        _render_card_grid(recs[:12], "🎯 因你所爱・相似影片")

        # --- 2. 视觉同源 ---
        if get(StateKeys.VISUAL_RECS) is None:
            set_state(StateKeys.VISUAL_RECS, [])

        if recs and not get(StateKeys.VISUAL_RECS):
            with st.spinner("正在分析视觉风格，寻找画面相似的影片..."):
                exclude_ids = {r.get('tmdb_id') for r in recs if r.get('tmdb_id')}
                visual_movies = get_visual_recommendations(username, top_k=6, exclude_ids=exclude_ids)
                if visual_movies:
                    reasons = generate_batch_reasons(visual_movies, get(StateKeys.USER_PROFILE_TEXT), "视觉同源")
                    for i, movie in enumerate(visual_movies):
                        movie['reason'] = reasons[i] if i < len(reasons) else "🎨 视觉风格匹配"
                    set_state(StateKeys.VISUAL_RECS, visual_movies)

        visual_recs = get(StateKeys.VISUAL_RECS)
        if visual_recs:
            st.markdown("#### 🎨 视觉同源・画风匹配")
            st.caption("基于你喜欢的电影画面风格，推荐视觉相似的影片")
            _render_card_grid(visual_recs, "")

        # --- 3. 冷门宝藏 ---
        st.markdown("#### 🎲 新鲜尝试・小众宝藏")
        exclude_ids = [m.get('tmdb_id') for m in recs if m.get('tmdb_id')]
        cold_movies = get_cold_recommendations(username, top_k=6, exclude_ids=exclude_ids)
        if cold_movies:
            cold_reasons = generate_batch_reasons(cold_movies, get(StateKeys.USER_PROFILE_TEXT), "冷门探索")
            for i, movie in enumerate(cold_movies):
                movie['reason'] = cold_reasons[i] if i < len(cold_reasons) else "🎯 探索新口味"
            _render_card_grid(cold_movies, "")
        else:
            st.info("暂无更多冷门宝藏推荐，继续评分更多电影来解锁吧～")
    else:
        st.info("暂无推荐，请稍后刷新")


def _fetch_and_enrich_recommendations(username, top_k=12):
    """获取推荐并丰富信息"""
    raw_recs = get_personalized_recommendations(username, top_k=top_k)
    enriched = []
    for m in raw_recs:
        tmdb_id = m.get('tmdbId') or m.get('movieId') or m.get('tmdb_id')
        if tmdb_id:
            detail = get_tmdb_movie_info(tmdb_id)
            if detail:
                enriched.append({
                    'tmdb_id': tmdb_id,
                    'title': detail.get('title', m.get('title', '')),
                    'genres_ch': detail.get('genres', ''),
                    'rating_ch': convert_to_5_star(detail.get('vote_average', 0)),
                    'poster_url': detail.get('poster_url'),
                })
            else:
                enriched.append({
                    'tmdb_id': tmdb_id,
                    'title': m.get('title', ''),
                    'genres_ch': m.get('genres', '').replace('|', ' · '),
                    'rating_ch': convert_to_5_star(m.get('vote_average', 0) or 0),
                    'poster_url': None,
                })
    return enriched


def _render_card_grid(movies, title=""):
    """渲染电影卡片网格（6列）"""
    if title:
        st.markdown(f"#### {title}")

    for row in range(0, len(movies), 6):
        cols = st.columns(6)
        for idx, movie in enumerate(movies[row:row + 6]):
            with cols[idx]:
                poster_url = movie.get('poster_url')
                vote_5 = movie.get('rating_ch', 0)
                stars = format_stars(vote_5)
                poster_html = f'<img class="rec-poster" src="{poster_url if poster_url else NO_POSTER_URL}" onerror="this.src=\'{NO_POSTER_URL}\'">'
                st.markdown(f"""
                <div class="rec-card" onclick="window.location.href='?detail_id={movie['tmdb_id']}'">
                    {poster_html}
                    <div class="rec-info">
                        <div class="rec-title">{movie['title']}</div>
                        <div class="rec-genre">{movie['genres_ch']}</div>
                        <div class="rec-rating">{stars} {vote_5}</div>
                        <div class="rec-reason">💡 {movie.get('reason', '推荐')[:50]}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)


# ==================== 首页调用函数 ====================

def get_personalized_movies(username, top_k=6):
    """供首页调用的精简版推荐"""
    if not get(StateKeys.USER_PROFILE_TEXT) or get(StateKeys.PROFILE_USER) != username:
        stats = get_user_stats(username)
        if stats and stats['total'] > 0:
            ratings_data = get_ratings_from_db(username)
            genre_counts = {}
            for tmdb_id, rating, timestamp in ratings_data:
                movie_info = get_tmdb_movie_info(tmdb_id)
                if movie_info and movie_info.get('genres'):
                    for g in movie_info['genres'].split(' · '):
                        genre_counts[g] = genre_counts.get(g, 0) + 1
            fav_genre = max(genre_counts, key=genre_counts.get) if genre_counts else "电影"
            set_state(StateKeys.USER_PROFILE_TEXT, f"偏爱{fav_genre}类型")
            set_state(StateKeys.PROFILE_USER, username)

    if get(StateKeys.PERSONALIZED_RECS):
        return get(StateKeys.PERSONALIZED_RECS)[:top_k]

    # 兜底
    from services.search import text_search
    hot_movies = text_search("popular movies", top_k=top_k, username=username)
    result = []
    for m in hot_movies:
        tmdb_id = m.get('tmdbId') or m.get('movieId')
        if tmdb_id:
            detail = get_tmdb_movie_info(tmdb_id)
            if detail:
                result.append({
                    'tmdb_id': tmdb_id,
                    'title': detail.get('title', m.get('title', '')),
                    'genres_ch': detail.get('genres', ''),
                    'rating_ch': convert_to_5_star(detail.get('vote_average', 0)),
                    'poster_url': detail.get('poster_url'),
                    'reason': '热门推荐，去个性推荐页评分解锁专属影片'
                })
    return result


if __name__ == "__main__":
    show()