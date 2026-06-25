# pages/hot.py - 精简版，只负责 UI
import streamlit as st
import random
from datetime import datetime
from collections import Counter

# === 服务层导入 ===
from services.tmdb import get_tmdb_now_playing, get_tmdb_popular, get_genre_map
from services.hot import (
    batch_generate_hot_comments,
    get_cold_movies_with_comments,
    save_snapshot_if_needed,
    get_snapshot_growth_rate,
    has_historical_data,
    cleanup_old_snapshots,
    init_snapshot_db,
    get_simulated_growth_rate,
)

# === 组件导入 ===
from components import NO_POSTER_URL, convert_to_5_star

# === 状态导入 ===
from state import get, set as set_state, StateKeys

# === 日志 ===
from utils.logger import get_logger

logger = get_logger("hot")


# ==================== 主函数 ====================

def show():
    # 初始化状态
    if get(StateKeys.CURRENT_PAGE_HOT) is None:
        set_state(StateKeys.CURRENT_PAGE_HOT, 1)
    if get(StateKeys.COLD_MOVIES) is None:
        set_state(StateKeys.COLD_MOVIES, None)

    # 页面标题
    st.markdown('<p class="page-title">✨ 热度影鉴</p>', unsafe_allow_html=True)
    st.markdown(
        '<p style="color:#98a1c3; margin-bottom: 1.5rem;">洞悉当下观影风向，AI解析高分影片魅力，热门冷门同步甄选</p>',
        unsafe_allow_html=True
    )

    # 初始化快照数据库
    init_snapshot_db()

    # --- 获取数据 ---
    movies = get_tmdb_now_playing()
    if not movies:
        movies = get_tmdb_popular()

    # 保存快照
    save_snapshot_if_needed(movies)
    cleanup_old_snapshots()
    has_history = has_historical_data()

    # 全站热门：按评分人数排序
    movies_by_votes = sorted(movies, key=lambda x: x.get('vote_count', 0), reverse=True)

    # 飙升榜
    MIN_VOTE_COUNT = 50
    movies_with_growth = []
    for m in movies:
        vote_count = m.get('vote_count', 0)
        if vote_count < MIN_VOTE_COUNT:
            continue
        real_growth = get_snapshot_growth_rate(m.get('id'), days=7)
        if real_growth is not None:
            growth = real_growth
        else:
            growth = get_simulated_growth_rate(m.get('popularity', 0), vote_count)
        m['growth_rate'] = growth
        movies_with_growth.append(m)
    movies_by_growth = sorted(movies_with_growth, key=lambda x: x.get('growth_rate', 0), reverse=True)

    top1 = movies_by_votes[0] if len(movies_by_votes) > 0 else None
    top2 = movies_by_growth[0] if len(movies_by_growth) > 0 else None

    # 全局热度指数
    top20 = movies_by_votes[:20]
    if top20:
        weighted_sum = 0
        total_votes = 0
        for m in top20:
            pop = m.get('popularity', 0)
            votes = m.get('vote_count', 0)
            weighted_sum += pop * votes
            total_votes += votes
        total_popularity_display = round(weighted_sum / total_votes, 1) if total_votes > 0 else 0
    else:
        total_popularity_display = 0

    # 热门类型统计
    genre_counter = Counter()
    for movie in movies_by_votes[:20]:
        for gid in movie.get('genre_ids', []):
            genre_counter[gid] += 1
    genre_map = get_genre_map()
    top_genres = genre_counter.most_common(3)
    genre_tags = ' · '.join([genre_map.get(gid, '未知') for gid, _ in top_genres])

    # 批量生成热门评论
    hot_movies_for_comments = movies_by_votes[:12]
    if top1 and top1 not in hot_movies_for_comments:
        hot_movies_for_comments.append(top1)
    if top2 and top2 not in hot_movies_for_comments:
        hot_movies_for_comments.append(top2)

    hot_comments_cache = batch_generate_hot_comments(hot_movies_for_comments)

    def get_hot_comment(movie):
        """从缓存中获取电影评论"""
        movie_id = movie.get('id')
        return hot_comments_cache.get(movie_id, "热门推荐")

    # --- CSS 样式 ---
    _render_styles()

    # --- 三卡片 ---
    _render_stats_cards(top1, top2, total_popularity_display, genre_tags, has_history, get_hot_comment)

    # --- 双标签栏 ---
    selected_tab = st.radio(
        "",
        options=["🏆 全站热门 (评分人数)", "📈 本周飙升榜"],
        horizontal=True,
        label_visibility="collapsed",
        key="hot_tab_selector"
    )

    display_movies = movies_by_votes[:12] if selected_tab == "🏆 全站热门 (评分人数)" else movies_by_growth[:12]

    # --- 电影网格 ---
    _render_movie_grid(display_movies, get_hot_comment)

    # --- 冷门宝藏 ---
    _render_cold_movies()

    # --- 分页和页脚 ---
    st.markdown("""
    <div class="pagination">
        <div class="page-item active">1</div>
        <div class="page-item">2</div>
        <div class="page-item">3</div>
        <div class="page-item"><i class="fas fa-chevron-right"></i></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <footer>
        🔥 全站热门按评分人数排序 | 飙升榜{'使用7天真实增长率' if has_history else '使用模拟数据（7天后自动切换真实）'}<br>
        ⏰ 数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </footer>
    """, unsafe_allow_html=True)

    # 处理详情跳转
    if st.query_params.get('hot_detail_id'):
        detail_id = st.query_params.get('hot_detail_id')
        from movie_detail import show_movie_detail
        movie_obj = {'tmdbId': int(detail_id), 'id': int(detail_id)}
        show_movie_detail(movie_obj)
        st.query_params.clear()
        st.rerun()


# ==================== 样式 ====================

def _render_styles():
    st.markdown("""
    <style>
    .stats-card {
        background: #11131f;
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #252838;
        transition: all 0.3s;
        height: 100%;
    }
    .stats-card:hover {
        transform: translateY(-4px);
        border-color: #7c4dff;
    }
    .stats-card h3 {
        font-size: 1rem;
        color: #c084fc;
        margin-bottom: 12px;
    }
    .trend-value {
        font-size: 1.3rem;
        font-weight: 700;
        margin-bottom: 8px;
    }
    .sub-text {
        font-size: 0.75rem;
        color: #98a1c3;
        margin-bottom: 12px;
    }
    .hot-badge {
        background: #1a1e2c;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.7rem;
        display: inline-block;
        color: #c084fc;
    }
    .movie-card {
        background: #11131f;
        border-radius: 12px;
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
        flex-shrink: 0;
    }
    .movie-info {
        padding: 10px;
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    .movie-title {
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .movie-meta {
        display: flex;
        gap: 8px;
        align-items: center;
        font-size: 0.65rem;
        color: #98a1c3;
        flex-wrap: wrap;
        margin-bottom: 6px;
    }
    .rating i {
        color: #fbbf24;
    }
    .trend-up {
        color: #ff6b6b;
    }
    .llm-hot-reason {
        background: #1a1e2c;
        padding: 6px 8px;
        border-radius: 8px;
        font-size: 0.6rem;
        color: #c4b5fd;
        margin-top: auto;
        line-height: 1.3;
    }
    .cold-banner {
        margin-top: 48px;
        border-radius: 32px;
        padding: 24px;
    }
    .pagination {
        display: flex;
        justify-content: center;
        gap: 8px;
        margin-top: 30px;
    }
    .page-item {
        background: #1a1e2c;
        padding: 6px 12px;
        border-radius: 8px;
        cursor: pointer;
    }
    .page-item.active {
        background: #7c4dff;
        color: white;
    }
    footer {
        text-align: center;
        margin-top: 30px;
        font-size: 0.7rem;
        color: #5b637a;
    }
    .skeleton-movie-card {
        background: #11131f;
        border-radius: 12px;
        border: 1px solid #252838;
        overflow: hidden;
        height: 100%;
        display: flex;
        flex-direction: column;
        animation: pulse 1.5s ease-in-out infinite;
    }
    .skeleton-poster {
        width: 100%;
        aspect-ratio: 2 / 3;
        background: #2a2f4e;
    }
    .skeleton-info {
        padding: 10px;
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    .skeleton-text {
        height: 14px;
        background: #2a2f4e;
        border-radius: 4px;
    }
    .skeleton-text.short {
        width: 60%;
    }
    @keyframes pulse {
        0% { opacity: 0.6; }
        50% { opacity: 1; }
        100% { opacity: 0.6; }
    }
    </style>
    """, unsafe_allow_html=True)


# ==================== 统计卡片 ====================

def _render_stats_cards(top1, top2, total_popularity_display, genre_tags, has_history, get_hot_comment):
    col1, col2, col3 = st.columns(3)

    with col1:
        if top1:
            title = top1.get('title', '未知')
            vote_5 = convert_to_5_star(top1.get('vote_average', 0))
            vote_count = top1.get('vote_count', 0)
            ai_comment = get_hot_comment(top1)
            st.markdown(f"""
            <div class="stats-card">
                <h3><i class="fas fa-chart-line"></i> 本周最热影片</h3>
                <div class="trend-value">{title}</div>
                <div class="sub-text">{vote_count:,} 人评分 | 均分 {vote_5}</div>
                <div class="hot-badge"><i class="fas fa-robot"></i> {ai_comment}</div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        if top2:
            title = top2.get('title', '未知')
            growth = top2.get('growth_rate', 0)
            badge_text = "真实飙升" if has_history else "模拟热度"
            st.markdown(f"""
            <div class="stats-card">
                <h3><i class="fas fa-rocket"></i> 飙升黑马</h3>
                <div class="trend-value">{title}</div>
                <div class="sub-text">7天热度增长 +{growth}%</div>
                <div class="hot-badge"><i class="fas fa-arrow-trend-up"></i> {badge_text}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="stats-card">
                <h3><i class="fas fa-rocket"></i> 飙升黑马</h3>
                <div class="trend-value">加载中...</div>
                <div class="sub-text">7天热度增长 --%</div>
            </div>
            """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stats-card">
            <h3><i class="fas fa-chart-simple"></i> 全局热度指数</h3>
            <div class="trend-value">{total_popularity_display} 🔥</div>
            <div class="sub-text">热门类型：{genre_tags}</div>
        </div>
        """, unsafe_allow_html=True)


# ==================== 电影网格 ====================

def _render_movie_grid(display_movies, get_hot_comment):
    for row in range(0, len(display_movies), 6):
        cols = st.columns(6)
        for idx, movie in enumerate(display_movies[row:row + 6]):
            with cols[idx]:
                title = movie.get('title', '未知')
                year = movie.get('release_date', '未知')[:4] if movie.get('release_date') else '未知'
                vote_10 = movie.get('vote_average', 0)
                vote_5 = convert_to_5_star(vote_10)
                poster_path = movie.get('poster_path')
                poster_url = f"https://image.tmdb.org/t/p/w200{poster_path}" if poster_path else None
                ai_comment = get_hot_comment(movie)
                badge_text = f"{movie.get('vote_count', 0):,} 人评分"
                movie_id = movie.get('id')
                click_js = f"window.location.href='?hot_detail_id={movie_id}'"

                st.markdown(f"""
                <div class="movie-card" onclick="{click_js}" style="cursor:pointer;">
                    <img class="movie-poster" src="{poster_url if poster_url else NO_POSTER_URL}" style="width:100%;" onerror="this.src='{NO_POSTER_URL}'">
                    <div class="movie-info">
                        <div class="movie-title">{title}</div>
                        <div class="movie-meta">
                            <span>{year}</span>
                            <span class="rating">⭐ {vote_5}</span>
                            <span>{badge_text}</span>
                        </div>
                        <div class="llm-hot-reason">
                            🤖 {ai_comment[:40]}{'...' if len(ai_comment) > 40 else ''}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)


# ==================== 冷门宝藏 ====================

def _render_cold_movies():
    cold_movies = get(StateKeys.COLD_MOVIES)

    if cold_movies is None:
        st.markdown("""
        <div class="cold-banner">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
                <i class="fas fa-gem" style="font-size: 28px; color: #fbbf24;"></i>
                <h3 style="font-weight: 600;">🎁 冷门宝藏 · 你可能错过的惊喜</h3>
                <span style="background: #fbbf2420; padding: 4px 12px; border-radius: 60px; font-size: 0.7rem;">口碑优秀但热度较低</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        cols = st.columns(6)
        for col in cols:
            with col:
                st.markdown("""
                <div class="skeleton-movie-card">
                    <div class="skeleton-poster"></div>
                    <div class="skeleton-info">
                        <div class="skeleton-text"></div>
                        <div class="skeleton-text short"></div>
                        <div class="skeleton-text short"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with st.spinner("正在挖掘冷门宝藏..."):
            cold_movies = get_cold_movies_with_comments(6)
            set_state(StateKeys.COLD_MOVIES, cold_movies)
            st.rerun()
    else:
        if cold_movies:
            st.markdown(f"""
            <div class="cold-banner">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
                    <i class="fas fa-gem" style="font-size: 28px; color: #fbbf24;"></i>
                    <h3 style="font-weight: 600;">🎁 冷门宝藏 · 你可能错过的惊喜</h3>
                    <span style="background: #fbbf2420; padding: 4px 12px; border-radius: 60px; font-size: 0.7rem;">口碑优秀但热度较低</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            cold_cols = st.columns(6)
            for idx, movie in enumerate(cold_movies[:6]):
                with cold_cols[idx]:
                    title = movie.get('title', '未知')
                    vote_10 = movie.get('vote_average', 0)
                    vote_5 = convert_to_5_star(vote_10)
                    poster_path = movie.get('poster_path')
                    poster_url = f"https://image.tmdb.org/t/p/w200{poster_path}" if poster_path else None
                    movie_id = movie.get('tmdb_id')
                    cold_comment = movie.get('ai_comment', '冷门佳作')
                    click_js = f"window.location.href='?hot_detail_id={movie_id}'"

                    st.markdown(f"""
                    <div class="movie-card" onclick="{click_js}" style="cursor:pointer;">
                        <img class="movie-poster" src="{poster_url if poster_url else NO_POSTER_URL}" style="width:100%;" onerror="this.src='{NO_POSTER_URL}'">
                        <div class="movie-info">
                            <div class="movie-title">{title}</div>
                            <div class="movie-meta">
                                <span class="rating">⭐ {vote_5}</span>
                            </div>
                            <div class="llm-hot-reason">
                                🤖 {cold_comment}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("暂时没有发现冷门宝藏影片，请稍后再来")


if __name__ == "__main__":
    show()