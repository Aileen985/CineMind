# history.py（找类似卡片缩小版）
import streamlit as st
import pandas as pd
import numpy as np
import json
import requests
from datetime import datetime
import plotly.graph_objects as go
from openai import OpenAI

# 替换旧的 rating_db 和 user_profile 导入
from db.ratings import get_user_ratings as get_ratings_from_db
from db.profiles import get_text_profile
from services.search import text_search
from movie_detail import show_movie_detail

# 从 components 导入
from components import format_stars

# 从 state 导入状态管理
from state import get, set, StateKeys

# 从 cache 导入缓存配置
from services.cache import CacheTTL

# 使用统一日志
from utils.logger import get_logger

# ==================== 日志 ====================
logger = get_logger("history")

# ==================== 配置 ====================
from config import TMDB_API_KEY, TMDB_IMAGE_BASE, DEEPSEEK_API_KEY

# DeepSeek 配置
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)


@st.cache_data(ttl=CacheTTL.MEDIUM)  # 1天缓存
def get_tmdb_movie_info(tmdb_id):
    if not tmdb_id or pd.isna(tmdb_id):
        return None
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=zh-CN"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            genre_names = [g['name'] for g in data.get('genres', [])]
            return {
                'title': data.get('title', ''),
                'genres': genre_names,
                'year': data.get('release_date', '')[:4] if data.get('release_date') else '',
                'poster_path': data.get('poster_path'),
                'vote_average': data.get('vote_average', 0),
                'overview': data.get('overview', '')
            }
    except Exception as e:
        logger.error(f"TMDB 获取失败: {e}")
    return None


def get_poster_icon(genres):
    icon_map = {
        '科幻': '🚀', '动画': '🎨', '喜剧': '😄', '爱情': '💕', '悬疑': '🔍',
        '惊悚': '😱', '动作': '⚡', '冒险': '🗺️', '奇幻': '✨', '剧情': '📖',
        '恐怖': '👻', '纪录片': '📹'
    }
    for g in genres:
        if g in icon_map:
            return icon_map[g]
    return '🎬'


def load_user_ratings(username):
    ratings_data = get_ratings_from_db(username)
    if not ratings_data:
        return []
    user_ratings = []
    for tmdb_id, rating, timestamp in ratings_data:
        movie_info = get_tmdb_movie_info(int(tmdb_id))
        if not movie_info:
            continue
        date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        genres = movie_info['genres']
        poster_icon = get_poster_icon(genres)
        user_ratings.append({
            "id": int(tmdb_id),
            "title": movie_info['title'],
            "year": int(movie_info['year']) if movie_info['year'].isdigit() else 0,
            "rating": rating,
            "date": date_str,
            "genres": genres,
            "poster_icon": poster_icon,
            "poster_path": movie_info.get('poster_path')
        })
    user_ratings.sort(key=lambda x: x['date'], reverse=True)
    return user_ratings


def get_stats(ratings):
    if not ratings:
        return {"total": 0, "avg": 0, "high_count": 0, "top_genre": "无", "top_three": []}
    total = len(ratings)
    avg = sum(r["rating"] for r in ratings) / total
    high_count = sum(1 for r in ratings if r["rating"] > 4)
    genre_freq = {}
    for movie in ratings:
        for g in movie["genres"]:
            genre_freq[g] = genre_freq.get(g, 0) + 1
    sorted_genres = sorted(genre_freq.items(), key=lambda x: x[1], reverse=True)
    top_genre = sorted_genres[0][0] if sorted_genres else "未知"
    top_three = sorted_genres[:3]
    return {
        "total": total,
        "avg": round(avg, 2),
        "high_count": high_count,
        "top_genre": top_genre,
        "top_three": top_three
    }


def prepare_trend_data(ratings):
    if not ratings:
        return [], []
    month_map = {}
    for r in ratings:
        month = r["date"][:7]
        if month not in month_map:
            month_map[month] = {"sum": 0, "count": 0}
        month_map[month]["sum"] += r["rating"]
        month_map[month]["count"] += 1
    months = sorted(month_map.keys())
    avg_ratings = [month_map[m]["sum"] / month_map[m]["count"] for m in months]
    return months, avg_ratings


def generate_llm_summary(ratings, stats, username):
    if not ratings:
        return "暂无评分数据，快去给电影评分吧！"
    recent_titles = [m["title"] for m in ratings[:5]]
    high_rated = [m["title"] for m in ratings if m["rating"] >= 4][:3]
    # 使用新的函数名 get_text_profile
    profile = get_text_profile(username)
    if profile:
        top_tags = profile.get('top_tags', [])
        top_atm = profile.get('top_atm_style', '')
        top_vis = profile.get('top_vis_style', '')
        profile_text = f"标签偏好：{', '.join(top_tags[:3])}。"
        if top_atm:
            profile_text += f" 偏爱 {top_atm} 氛围。"
        if top_vis:
            profile_text += f" 视觉风格倾向 {top_vis}。"
    else:
        profile_text = ""

    try:
        prompt = f"""你是一个专业的电影品味分析师。根据以下用户数据，生成一段有个性、有洞察力的观影总结（50-80字）。

数据：
- 总评分：{stats['total']} 部
- 平均分：{stats['avg']} / 5
- 高分电影（≥4分）：{stats['high_count']} 部
- 最喜欢的类型：{stats['top_genre']}
- 最近看过：{', '.join(recent_titles[:3])}
- 高分电影举例：{', '.join(high_rated) if high_rated else '无'}
- 用户画像：{profile_text}

要求：
1. 语气亲切自然，像朋友聊天
2. 分析观影偏好，指出风格倾向
3. 适当夸奖或调侃用户的品味
4. 末尾加一个简短的建议
5. 不要超过80字

请直接输出总结："""
        response = deepseek_client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
            extra_body={"thinking": {"type": "disabled"}}
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        logger.error(f"DeepSeek 总结失败: {e}")
        return f"📊 基于你的 {stats['total']} 条评分记录，平均 {stats['avg']} 分，最爱 {stats['top_genre']} 类型。最近看了《{recent_titles[0]}》，值得继续探索！"


# 注意：render_star_rating 已迁移到 components/star_rating.py，使用 format_stars


def export_to_json(ratings):
    export_data = [{"id": m["id"], "title": m["title"], "year": m["year"],
                    "rating": m["rating"], "date": m["date"], "genres": m["genres"]}
                   for m in ratings]
    return json.dumps(export_data, ensure_ascii=False, indent=2)


# ==================== 找类似功能（卡片缩小） ====================
# ==================== 找类似功能（一行六列紧凑卡片） ====================
@st.dialog("🎬 类似电影推荐", width="large")
def show_similar_movies(movie_id, movie_title):
    st.write(f"基于《{movie_title}》的推荐")
    results = text_search(movie_title, top_k=6)
    if not results:
        st.info("未找到类似电影")
        return

    # 一行六列
    cols = st.columns(6)
    for idx, movie in enumerate(results[:6]):
        with cols[idx]:
            tmdb_id = movie.get('tmdbId') or movie.get('movieId')
            tmdb_info = get_tmdb_movie_info(tmdb_id) if tmdb_id else None
            if tmdb_info:
                display_title = tmdb_info['title']
                display_genres = ' · '.join(tmdb_info['genres'])
                display_year = tmdb_info['year']
                poster_path = tmdb_info.get('poster_path')
                poster_url = f"https://image.tmdb.org/t/p/w200{poster_path}" if poster_path else None
            else:
                display_title = movie.get('title', '未知')
                display_genres = movie.get('genres', '').replace('|', ' · ')
                display_year = ''
                poster_url = None

            # 超紧凑卡片
            with st.container(border=True):
                # 小海报
                if poster_url:
                    st.image(poster_url, use_container_width=True)
                else:
                    st.markdown('<div style="background:#1a1e2c; aspect-ratio:2/3; display:flex; align-items:center; justify-content:center; font-size:1.5rem; color:#555; border-radius:4px;">🎬</div>', unsafe_allow_html=True)

                # 标题（小字体）
                st.markdown(f'<div style="font-size:0.75rem; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{display_title}</div>', unsafe_allow_html=True)
                if display_year:
                    st.caption(f"📅 {display_year}")
                    st.caption(display_genres)

                # 查看详情按钮（小）
                if st.button(f"详情", key=f"sim_detail_{movie_id}_{idx}", use_container_width=True):
                    st.query_params['detail_id'] = tmdb_id if tmdb_id else movie_id
                    st.rerun()

# ==================== 主页面 ====================
def show():
    # 监听 query_params，弹出电影详情
    if st.query_params.get('detail_id'):
        detail_id = st.query_params.get('detail_id')
        movie_obj = {'tmdbId': int(detail_id), 'id': int(detail_id)}
        show_movie_detail(movie_obj)
        st.query_params.clear()
        st.rerun()
        return

    # 使用 state 获取用户名
    username = get(StateKeys.USERNAME, 'guest')
    if username == 'guest':
        st.warning("请先登录")
        st.stop()

    with st.spinner("加载你的观影记录..."):
        user_ratings = load_user_ratings(username)

    if not user_ratings:
        st.info("暂无评分记录，去首页给电影评分吧～")
        return

    stats = get_stats(user_ratings)

    # CSS 样式（与原来完全一致）
    st.markdown("""
            <style>
        .app-container { max-width: 1400px; margin: 0 auto; padding: 24px 32px 48px; }
        .logo h1 { font-size: 1.8rem; font-weight: 700; background: linear-gradient(135deg, #c084fc, #60a5fa); -webkit-background-clip: text; background-clip: text; color: transparent; }
        .nav-links { display: flex; gap: 28px; background: rgba(255,255,255,0.05); padding: 10px 24px; border-radius: 60px; backdrop-filter: blur(4px); }
        .nav-links a { color: #cdd6f4; text-decoration: none; font-weight: 500; transition: 0.2s; }
        .nav-links a:hover, .nav-links a.active { color: #c084fc; }
        .user-avatar { width: 44px; height: 44px; background: linear-gradient(145deg, #2d2f4e, #1a1d35); border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(192,132,252,0.4); cursor: pointer; }
        .stats-row { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 32px; }
        .stat-card { background: rgba(18,22,40,0.7); backdrop-filter: blur(12px); border-radius: 28px; padding: 20px 24px; height: 160px; flex: 1; min-width: 160px; border: 1px solid rgba(255,255,255,0.08); }
        .stat-number { font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #FDE047, #F97316); -webkit-background-clip: text; background-clip: text; color: transparent; }
        .stat-label { color: #98a1c3; font-size: 0.85rem; margin-top: 6px; }
        .genre-fav { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
        .genre-chip { background: #7c3aed30; border-radius: 40px; padding: 4px 12px; font-size: 0.69rem; }
        .chart-box { min-height: 320px; margin-bottom: -280px !important; background: rgba(18,22,40,0.8); border-radius: 28px; padding: 20px 24px; border: 1px solid rgba(255,255,255,0.06); }
        .llm-summary-box { min-height: 320px; margin-bottom: -280px !important; background: linear-gradient(145deg, #1b1f3c, #11152e); border-radius: 28px; border: 1px solid rgba(139,92,246,0.4); }
        .summary-text { font-size: 0.9rem; line-height: 1.5; color: #cddcff; margin: 0 0 18px 0; }
        .refresh-summary { background: #7c3aed; border: none; padding: 6px 16px; border-radius: 40px; color: white; font-size: 0.7rem; cursor: pointer; margin-top: 20px; }
        .history-header { display: flex; justify-content: space-between; align-items: baseline; margin: 28px 0 20px 0; }
        .export-btn { background: transparent; border: 1px solid #7c3aed; padding: 6px 18px; border-radius: 30px; color: #c4b5fd; cursor: pointer; }
        .timeline-list { display: flex; flex-direction: column; gap: 12px; }
        .history-item { background: rgba(24,29,50,0.7); border-radius: 20px; padding: 16px 20px; display: flex; align-items: center; flex-wrap: wrap; gap: 16px; transition: 0.2s; border: 1px solid rgba(255,255,255,0.05); min-height: 80px; margin-bottom: -160px !important; }
        .history-item:hover { background: rgba(36,42,70,0.9); border-color: #7c3aed; }
        .history-poster { width: 50px; height: 70px; background: radial-gradient(circle at 30% 20%, #2a2f4e, #13172e); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
        .history-info { flex: 3; }
        .history-title { font-weight: 700; margin-bottom: 4px; }
        .history-meta { font-size: 0.7rem; color: #98a1c3; }
        .history-rating { font-size: 1.2rem; font-weight: 600; color: #fbbf24; min-width: 60px; text-align: center; }
        div[class*="st-key-similar_"] .stButton > button { background: rgba(139,92,246,0.2); border: none; padding: 6px 14px; border-radius: 26px; color: #c4b5fd; font-size: 0.7rem; cursor: pointer; transition: 0.2s; }
        div[class*="st-key-similar_"] .stButton > button:hover { background: #7c3aed; color: white; }
        .pagination { margin-top: 30px; display: flex; justify-content: center; gap: 12px; }
        .page-item { background: rgba(255,255,255,0.05); width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 12px; cursor: pointer; }
        .footer { text-align: center; margin-top: 30px; }
        @media (max-width: 760px) { .app-container { padding: 16px; } .history-item { flex-direction: column; align-items: flex-start; } }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<p class="page-title"><i class="fas fa-history">评分历史 · 你的光影足迹</p>', unsafe_allow_html=True)
    st.markdown('<p style="color:#98a1c3; margin-bottom: 1.5rem;">记录每一刻的观影感受，AI 为你总结偏好，基于历史发现更多好电影</p>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""<div class="stat-card"><div class="stat-number">{stats['total']}</div><div class="stat-label">🎬 总评分数量</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="stat-card"><div class="stat-number">{stats['avg']}</div><div class="stat-label">⭐ 平均评分</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="stat-card"><div class="stat-number">{stats['high_count']}</div><div class="stat-label">❤️ 高分电影 (>4分)</div></div>""", unsafe_allow_html=True)
    with col4:
        genre_chips = "".join([f'<span class="genre-chip">{g[0]} ({g[1]})</span>' for g in stats['top_three']])
        st.markdown(f"""<div class="stat-card"><div class="stat-number">{stats['top_genre']}</div><div class="stat-label">🏆 最喜欢的类型</div><div style="margin-top: 0.5rem;">{genre_chips}</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 0.9])

    with left:
        st.markdown('<div class="chart-box">', unsafe_allow_html=True)
        st.markdown("#### 📈 月度评分趋势")
        months, avg_ratings = prepare_trend_data(user_ratings)
        if len(months) > 1:
            min_val = min(avg_ratings) if avg_ratings else 0
            max_val = max(avg_ratings) if avg_ratings else 5
            y_min = max(0, min_val - 0.5)
            y_max = min(5, max_val + 0.5)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=months, y=avg_ratings, mode='lines+markers', name='月均评分',
                line=dict(color='#c084fc', width=3), marker=dict(color='#fbbf24', size=8, symbol='circle'),
                fill='tozeroy', fillcolor='rgba(192,132,252,0.1)'
            ))
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#cdd6f4'),
                xaxis=dict(title="月份", gridcolor='rgba(255,255,255,0.1)', tickangle=45),
                yaxis=dict(title="平均评分", gridcolor='rgba(255,255,255,0.1)', range=[y_min, y_max]),
                height=240, margin=dict(l=10, r=10, t=10, b=10)
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("暂无足够数据生成趋势图（需要至少2个月的评分记录）")
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="llm-summary-box">', unsafe_allow_html=True)
        st.markdown("#### 🤖 LLM 年度观影总结")
        # 使用 state 获取总结和用户
        summary_text = get(StateKeys.SUMMARY_TEXT, "")
        summary_user = get(StateKeys.SUMMARY_USER, "")
        if not summary_text or summary_user != username:
            summary_text = generate_llm_summary(user_ratings, stats, username)
            set(StateKeys.SUMMARY_TEXT, summary_text)
            set(StateKeys.SUMMARY_USER, username)
        st.markdown(f'<div class="summary-text">{summary_text}</div>', unsafe_allow_html=True)
        st.markdown("        ")
        if st.button("🔄 重新生成总结", key="refresh_summary"):
            summary_text = generate_llm_summary(user_ratings, stats, username)
            set(StateKeys.SUMMARY_TEXT, summary_text)
            set(StateKeys.SUMMARY_USER, username)
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br><br><br>", unsafe_allow_html=True)

    col_left, col_right = st.columns([5.3, 1])
    with col_left:
        st.markdown("#### 📋 全部评分记录")
    with col_right:
        export_data = export_to_json(user_ratings)
        st.download_button(
            label="📥 导出数据 (JSON)",
            data=export_data,
            file_name=f"cine_ratings_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )

    PAGE_SIZE = 6
    # 使用 state 获取页码
    rating_page = get(StateKeys.RATING_PAGE, 1)
    total_pages = (len(user_ratings) + PAGE_SIZE - 1) // PAGE_SIZE
    start_idx = (rating_page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    page_data = user_ratings[start_idx:end_idx]

    for movie in page_data:
        # 使用 format_stars 替代本地 render_star_rating
        stars = format_stars(movie["rating"])
        st.markdown('<div class="history-item">', unsafe_allow_html=True)
        col_poster, col_info, col_rating, col_btn = st.columns([0.28, 3, 0.48, 0.48])
        with col_poster:
            st.markdown(f'<div class="history-poster" style="font-size:1.8rem;">{movie["poster_icon"]}</div>', unsafe_allow_html=True)
        with col_info:
            year_str = f" ({movie['year']})" if movie['year'] > 0 else ""
            st.markdown(f'<div class="history-title">{movie["title"]}{year_str}</div>', unsafe_allow_html=True)
            genres_str = " · ".join(movie["genres"])
            st.markdown(f'<div class="history-meta">{genres_str} &nbsp;|&nbsp; 评分时间: {movie["date"]}</div>', unsafe_allow_html=True)
        with col_rating:
            st.markdown(f'<div class="history-rating">{stars}<br><span style="font-size:0.8rem;">{movie["rating"]} ★</span></div>', unsafe_allow_html=True)
        with col_btn:
            if st.button(f"🔍 找类似", key=f"similar_{movie['id']}"):
                show_similar_movies(movie['id'], movie['title'])
        st.markdown('</div>', unsafe_allow_html=True)

    if total_pages > 1:
        col_prev, col_page_info, col_next = st.columns([1, 9, 1])
        with col_prev:
            if st.button("◀ 上一页", key="history_prev_btn") and rating_page > 1:
                set(StateKeys.RATING_PAGE, rating_page - 1)
                st.rerun()
        with col_page_info:
            st.markdown(f"<div style='text-align: center'>第 {rating_page} / {total_pages} 页</div>", unsafe_allow_html=True)
        with col_next:
            if st.button("下一页 ▶", key="history_next_btn") and rating_page < total_pages:
                set(StateKeys.RATING_PAGE, rating_page + 1)
                st.rerun()

    st.markdown("---")
    st.markdown(f'<div style="text-align: center; font-size:0.7rem; color:#5b637a; margin-top:-10px;">共 {len(user_ratings)} 条记录 · 第 {rating_page}/{total_pages} 页</div>', unsafe_allow_html=True)
    st.markdown('<div class="footer">⭐ 点击「找类似」将基于该电影发起文本检索，召回相似影片并弹出推荐。</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    show()