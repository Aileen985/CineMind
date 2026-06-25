# components/star_rating.py
"""
星级显示组件
"""
import streamlit as st


def format_stars(rating_5):
    """
    传入5分制评分，返回星星字符串（纯文本，不含颜色）
    """
    full = int(rating_5)
    half = rating_5 - full >= 0.5
    empty = 5 - full - (1 if half else 0)
    return "★" * full + ("½" if half else "") + "☆" * empty


def star_html(rating_5):
    """
    返回带黄色样式的星星HTML
    """
    stars = format_stars(rating_5)
    return f'<span style="color:#fbbf24;">{stars}</span>'


def render_stars(rating_5, use_html=True):
    """
    渲染星级
    use_html: True 返回 HTML 字符串，False 返回纯文本
    """
    if use_html:
        return star_html(rating_5)
    return format_stars(rating_5)


def get_star_display(rating_5):
    """兼容旧函数名"""
    return format_stars(rating_5)


def convert_to_5_star(rating_10):
    """将10分制转为5分制"""
    return round(rating_10 / 2, 1)