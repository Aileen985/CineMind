# components/__init__.py
"""
UI 组件库
"""
from .placeholders import NO_POSTER_URL, NO_POSTER_SVG, SKELETON_CSS
from .star_rating import format_stars, star_html, render_stars, get_star_display, convert_to_5_star
from .movie_card import render_movie_card, render_clickable_movie_card
from .filter_buttons import render_filter_buttons