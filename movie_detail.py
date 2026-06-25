# movie_detail.py - 精简版，只负责 UI 弹窗
import streamlit as st
import os
import requests
from datetime import datetime
from openai import OpenAI

# === 服务层导入 ===
from services.tmdb import get_movie_by_tmdb_id_cached
from services.atmosphere import (
    analyze_atmosphere_style,
    analyze_visual_style,
    generate_movie_tags,
    get_or_analyze_atmosphere_with_cache,
    get_or_analyze_visual_with_cache,
)
from db.ratings import get_my_rating, save_rating
from db.comments import get_my_comment, save_comment
from db.preferences import get_my_preference, save_preference
from db.movie_cache import get_cached_classify, save_classify_to_db

# === 状态导入 ===
from state import get, StateKeys

# === 日志 ===
from utils.logger import get_logger

# === 配置 ===
from config import POSTER_DIR, TMDB_API_KEY

logger = get_logger("movie_detail")

# === DeepSeek 客户端（仅用于弹窗内直接调用，但实际可迁移到 service）===
from config import DEEPSEEK_API_KEY
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)


# ==================== 主弹窗函数 ====================

@st.dialog("🎬 电影详情", width="large")
def show_movie_detail(movie):
    """电影详情弹窗"""

    # 获取当前用户
    username = get(StateKeys.USERNAME, "default_user")

    # 获取 tmdbId
    tmdb_id = movie.get('tmdbId') or movie.get('id')
    if not tmdb_id:
        st.error("无法获取电影ID")
        return

    # 获取 TMDB 数据
    tmdb_data = get_movie_by_tmdb_id_cached(tmdb_id)

    # 解析电影信息
    if tmdb_data:
        display_title = tmdb_data.get('title', movie.get('title', ''))
        display_title_en = tmdb_data.get('original_title', '')
        display_overview = tmdb_data.get('overview', '')
        display_genres = ' · '.join([g['name'] for g in tmdb_data.get('genres', [])])
        display_genres_raw = '|'.join([g['name'] for g in tmdb_data.get('genres', [])])
        display_year = tmdb_data.get('release_date', '')[:4] if tmdb_data.get('release_date') else ''
        display_rating = tmdb_data.get('vote_average', 0)
        display_vote_count = tmdb_data.get('vote_count', 0)
        display_runtime = tmdb_data.get('runtime', 0)
        display_tagline = tmdb_data.get('tagline', '')
        poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_data.get('poster_path')}" if tmdb_data.get('poster_path') else None

        # 获取导演和演员
        directors = []
        actors = []
        try:
            credits_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?api_key={TMDB_API_KEY}&language=zh-CN"
            resp = requests.get(credits_url, timeout=5)
            if resp.status_code == 200:
                credits = resp.json()
                directors = [crew['name'] for crew in credits.get('crew', []) if crew['job'] == 'Director']
                actors = [cast['name'] for cast in credits.get('cast', [])[:5]]
        except:
            pass
    else:
        display_title = movie.get('title', '')
        display_title_en = movie.get('original_title', '')
        display_overview = movie.get('overview', '')
        display_genres = movie.get('genres', '').replace('|', ' · ')
        display_genres_raw = movie.get('genres', '')
        display_year = movie.get('year', '')
        display_rating = movie.get('rating', 0)
        display_vote_count = 0
        display_runtime = 0
        display_tagline = ''
        poster_url = movie.get('poster_url')
        directors = []
        actors = []

    # 本地海报优先
    local_poster = f"{POSTER_DIR}/{tmdb_id}.jpg"
    if os.path.exists(local_poster):
        poster_url = local_poster

    # 获取分类数据（先缓存，没有再分析）
    cached = get_cached_classify(tmdb_id)
    if cached:
        visual_style = cached.get('visual_style')
        atmosphere_style = cached.get('atmosphere_style')
        tags = cached.get('tags')
        logger.info(f"📦 使用缓存数据: {tmdb_id}")
    else:
        with st.spinner("分析电影风格中..."):
            visual_style = analyze_visual_style(poster_url) if poster_url else None
            atmosphere_style = analyze_atmosphere_style(display_title, display_overview)
            tags = generate_movie_tags(display_title, display_genres, display_overview)
            save_classify_to_db(tmdb_id, display_title, display_genres_raw, visual_style, atmosphere_style, tags)

    # 获取用户数据
    current_rating = get_my_rating(username, tmdb_id)
    current_comment = get_my_comment(username, tmdb_id)
    current_preference = get_my_preference(username, tmdb_id)

    # ========== UI 布局 ==========
    col1, col2 = st.columns([1, 2])

    with col1:
        if poster_url:
            st.image(poster_url, use_container_width=True)
        else:
            st.image("https://via.placeholder.com/300x450?text=No+Poster", use_container_width=True)

        st.markdown("---")
        st.markdown("### ⭐ 你的评分")

        rating_value = current_rating if current_rating else 2.5
        rating = st.slider("你的评分", 0.5, 5.0, rating_value, 0.1,
                           key=f"rating_{tmdb_id}",
                           label_visibility="collapsed")

        if st.button("💾 保存评分", key=f"save_rating_{tmdb_id}", use_container_width=True):
            if save_rating(username, tmdb_id, rating):
                st.success(f"已评分 {rating} 分！", icon="✅")
                st.rerun()
            else:
                st.error("保存失败，请重试")

    with col2:
        st.markdown(f"## {display_title}")
        if display_title_en and display_title_en != display_title:
            st.caption(f"📝 {display_title_en}")

        if display_tagline:
            st.markdown(f"*“{display_tagline}”*")

        if visual_style:
            st.caption(f"🖼️ 视觉风格：{visual_style}")
        if atmosphere_style:
            st.caption(f"🎭 氛围风格：{atmosphere_style}")
        if tags:
            tags_text = ' · '.join(tags[:8])
            st.markdown(f"**🏷️ 标签**：{tags_text}")

        st.markdown("---")

        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            if display_year:
                st.metric("📅 年份", str(display_year))
        with col_info2:
            if display_runtime and display_runtime > 0:
                hours = display_runtime // 60
                minutes = display_runtime % 60
                runtime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}分钟"
                st.metric("⏱️ 时长", runtime_str)
        with col_info3:
            try:
                rating_value = float(display_rating) if display_rating else 0
                st.metric("⭐ TMDB评分", f"{rating_value:.1f}")
                if display_vote_count:
                    st.caption(f"({display_vote_count} 人评价)")
            except (ValueError, TypeError):
                st.metric("⭐ TMDB评分", "暂无")

        if display_genres and display_genres != '未知':
            st.markdown(f"**🎭 类型**：{display_genres}")

        if directors:
            st.markdown(f"**🎬 导演**：{', '.join(directors)}")
        if actors:
            st.markdown(f"**🎭 主演**：{' · '.join(actors)}")

        st.markdown("---")
        if display_overview:
            st.markdown("**📖 剧情简介**")
            st.write(display_overview)

    # 评语区域
    st.markdown("---")
    st.markdown("### 📝 你的评语")
    comment = st.text_area("写下你的观后感", value=current_comment or "", height=100,
                           key=f"comment_{tmdb_id}", label_visibility="collapsed")

    if st.button("💾 保存评语", key=f"save_comment_{tmdb_id}", use_container_width=True):
        if comment.strip():
            if save_comment(username, tmdb_id, comment):
                st.success("评语已保存！", icon="✅")
                st.rerun()
            else:
                st.error("保存失败，请重试")

    # 喜欢/不喜欢区域
    st.markdown("### ❤️ 我的感受")
    col_like, col_dislike = st.columns(2)

    with col_like:
        if current_preference == 'like':
            st.success("✅ 已喜欢")
            if st.button("取消喜欢", key=f"unlike_{tmdb_id}", use_container_width=True):
                if save_preference(username, tmdb_id, None):
                    st.success("已取消喜欢", icon="✅")
                    st.rerun()
        else:
            if st.button("❤️ 喜欢", key=f"like_{tmdb_id}", use_container_width=True):
                if save_preference(username, tmdb_id, 'like'):
                    st.success("感谢喜欢！我们会推荐更多类似电影", icon="✅")
                    st.rerun()

    with col_dislike:
        if current_preference == 'dislike':
            st.warning("⚠️ 已不喜欢")
            if st.button("取消不喜欢", key=f"undislike_{tmdb_id}", use_container_width=True):
                if save_preference(username, tmdb_id, None):
                    st.success("已取消不喜欢", icon="✅")
                    st.rerun()
        else:
            if st.button("💔 不喜欢", key=f"dislike_{tmdb_id}", use_container_width=True):
                if save_preference(username, tmdb_id, 'dislike'):
                    st.success("已记录，下次会避开这类电影", icon="✅")
                    st.rerun()