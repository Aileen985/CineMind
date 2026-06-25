# components/movie_card.py
"""
电影卡片组件
"""
import streamlit as st
from components.placeholders import NO_POSTER_URL
from components.star_rating import star_html, convert_to_5_star


def render_movie_card(movie, key_prefix, height=480, show_reason=True):
    """
    通用电影卡片渲染函数

    Args:
        movie: dict，包含 title, poster_url/poster_path, genres, vote_average, reason
        key_prefix: 卡片唯一前缀
        height: 卡片高度
        show_reason: 是否显示推荐理由
    """
    # 处理海报 URL
    poster_url = movie.get('poster_url')
    if not poster_url and movie.get('poster_path'):
        poster_url = f"https://image.tmdb.org/t/p/w300{movie['poster_path']}"

    title = movie.get('title', '未知')

    # 处理 genres
    genres_list = movie.get('genres', [])
    if isinstance(genres_list, str):
        genres_display = genres_list.replace('|', ' · ')
    elif isinstance(genres_list, list):
        genres_display = ' · '.join(genres_list)
    else:
        genres_display = ''

    reason = movie.get('reason', '值得一看')

    # 获取评分，统一转为5分制
    vote_10 = movie.get('vote_average', 0)
    if vote_10 > 5:
        vote_5 = convert_to_5_star(vote_10)
    else:
        vote_5 = round(vote_10, 1)

    stars_html = star_html(vote_5)
    movie_id = movie.get('id') or movie.get('tmdb_id') or movie.get('movieId')

    with st.container(border=True, height=height):
        if poster_url:
            st.image(poster_url, use_container_width=True)
        else:
            st.image(NO_POSTER_URL, use_container_width=True)

        st.markdown(f'<div class="movie-title">{title}</div>', unsafe_allow_html=True)
        if genres_display:
            st.caption(genres_display)

        st.markdown(f'<div style="color:#fbbf24; font-size:0.9rem;">{stars_html} {vote_5}</div>',
                    unsafe_allow_html=True)

        if show_reason:
            st.markdown(
                f"<div class='movie-reason' style='background:#1a1e2c; padding:6px 8px; border-radius:8px; font-size:0.65rem; color:#c4b5fd; margin-top:8px;'>💡 {reason[:50]}</div>",
                unsafe_allow_html=True
            )

    return poster_url, vote_5


def render_clickable_movie_card(movie, key_prefix, detail_url_param="detail_id", height=480):
    """
    可点击跳转详情的电影卡片
    """
    movie_id = movie.get('id') or movie.get('tmdb_id') or movie.get('movieId')
    if movie_id:
        click_js = f"window.location.href='?{detail_url_param}={movie_id}'"
    else:
        click_js = ""

    # 处理海报
    poster_url = movie.get('poster_url')
    if not poster_url and movie.get('poster_path'):
        poster_url = f"https://image.tmdb.org/t/p/w300{movie['poster_path']}"

    title = movie.get('title', '未知')
    genres_display = movie.get('genres', '')
    if isinstance(genres_display, list):
        genres_display = ' · '.join(genres_display)
    elif isinstance(genres_display, str):
        genres_display = genres_display.replace('|', ' · ')

    reason = movie.get('reason', '值得一看')
    vote_5 = movie.get('rating_ch') or movie.get('rating') or 0

    with st.container(border=True, height=height):
        if poster_url:
            st.image(poster_url, use_container_width=True)
        else:
            st.image(NO_POSTER_URL, use_container_width=True)

        if click_js:
            st.markdown(
                f'<div class="movie-title" onclick="{click_js}" style="cursor:pointer;">{title}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(f'<div class="movie-title">{title}</div>', unsafe_allow_html=True)

        if genres_display:
            st.caption(genres_display)

        st.markdown(f'<div style="color:#fbbf24; font-size:0.9rem;">{star_html(vote_5)} {vote_5}</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f"<div style='background:#1a1e2c; padding:6px 8px; border-radius:8px; font-size:0.65rem; color:#c4b5fd; margin-top:8px;'>💡 {reason[:50]}</div>",
            unsafe_allow_html=True
        )