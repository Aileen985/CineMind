# app.py
import streamlit as st
import sys
import traceback
from streamlit_floating_container import FloatingContainer
from floating_chat import show_floating_chat
import os

# 导入状态管理
from state import init_state, get, set, StateKeys

# 导入数据库层
from db import (
    init_users, init_ratings, init_preferences, init_comments,
    init_movie_cache, init_pools, init_profiles,
)
from db.users import register_user, login_user

# 导入统一日志和错误处理
from utils.logger import get_logger
from utils.error_handling import show_error_page

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pages import  history, hot, categories, home, personal

# ========== 日志 ==========
logger = get_logger("app")


# ---------- 页面配置 ----------
st.set_page_config(
    page_title="CineMind · 多模态RAG电影推荐",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------- 初始化所有状态 ----------
init_state()
init_users()
init_ratings()
init_preferences()
init_comments()
init_movie_cache()
init_pools()
init_profiles()


# ---------- 自定义深色主题 CSS ----------
st.markdown("""
<style>
    /* 全局背景 */
    .stApp {
        background: linear-gradient(145deg, #0a0c12 0%, #11131f 100%);
    }
    [data-testid="collapsedControl"] { display: none; }
    section[data-testid="stSidebar"] { display: none; }

    /* 品牌文字 */
    .brand-text {
        font-size: 1.6rem;
        font-weight: 700;
        background: linear-gradient(135deg, #e0b3ff, #7c4dff);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }

    /* 搜索框样式 */
    .stTextInput input {
        background-color: #181c28 !important;
        border: 1px solid #2d2f42 !important;
        color: white !important;
        border-radius: 40px !important;
        padding: 8px 16px !important;
    }

    /* 头像按钮样式（圆形） */
    button[aria-label="popover"] {
        background: #7c4dff !important;
        color: white !important;
        width: 42px !important;
        height: 42px !important;
        border-radius: 50% !important;
        padding: 0 !important;
        font-weight: 600;
        font-size: 1rem;
        display: inline-flex !important;
        align-items: center;
        justify-content: center;
    }

    .section-header {
        font-size: 1.6rem;
        font-weight: 600;
        margin: 2rem 0 1rem 0;
        background: linear-gradient(135deg, #e0b3ff, #7c4dff);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        text-align: left;
    }
    .movie-card {
        background: #12141e;
        border-radius: 20px;
        overflow: hidden;
        transition: transform 0.2s, box-shadow 0.2s;
        border: 1px solid #252838;
        margin-bottom: 1rem;
    }
    .movie-card:hover {
        transform: translateY(-6px);
        box-shadow: 0 20px 30px -12px rgba(0,0,0,0.5);
        border-color: #5f4b9e;
    }
    .card-info {
        padding: 14px;
    }
    .movie-title {
        font-weight: 600;
        font-size: 1rem;
        margin-bottom: 4px;
    }
    .movie-genre {
        font-size: 0.7rem;
        color: #aaa;
    }
    .ai-reason {
        background: #1a1e2c;
        padding: 6px 10px;
        border-radius: 30px;
        font-size: 0.7rem;
        color: #c4b5fd;
        margin-top: 10px;
        line-height: 1.3;
    }
    footer {
        text-align: center;
        margin-top: 3rem;
        color: #4a4e6e;
        font-size: 0.8rem;
    }
    .stButton > button {
        background: #7c4dff;
        color: white;
        border-radius: 40px;
        border: none;
    }
    .auth-form {
        background: #12141e;
        padding: 2rem;
        border-radius: 32px;
        max-width: 450px;
        margin: 4rem auto;
        border: 1px solid #2a2e44;
    }
    .subtitle {
        color:#8e94b0;  
    }
    /* 搜索按钮内联样式 */
    .search-container {
        display: flex;
        gap: 8px;
        align-items: center;
    }
    .search-container .stTextInput {
        flex: 1;
    }
    .search-container .stButton {
        flex-shrink: 0;
    }
</style>
<link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
""", unsafe_allow_html=True)


# ---------- 登录/注册界面 ----------
def auth_page():
    st.markdown("<div class='section-header' style='text-align:center;'>🎬 欢迎来到 CineMind</div>",
                unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#8e94b0;'>基于多模态RAG的智能电影推荐系统</p>",
                unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔐 登录", "📝 注册"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")
            if submitted:
                success, msg, _ = login_user(username, password)
                if success:
                    set(StateKeys.LOGGED_IN, True)
                    set(StateKeys.USERNAME, username)
                    st.rerun()
                else:
                    st.error(msg)

    with tab2:
        with st.form("register_form"):
            new_username = st.text_input("用户名")
            new_password = st.text_input("密码", type="password")
            confirm_password = st.text_input("确认密码", type="password")
            submitted_reg = st.form_submit_button("注册")
            if submitted_reg:
                if new_password != confirm_password:
                    st.error("两次密码不一致")
                elif len(new_username) < 3:
                    st.error("用户名至少3个字符")
                else:
                    success, msg = register_user(new_username, new_password)
                    if success:
                        st.success(msg)
                        set(StateKeys.LOGGED_IN, True)
                        set(StateKeys.USERNAME, new_username)
                        st.rerun()
                    else:
                        st.error(msg)


# ---------- 登录后的主界面 ----------
def main():
    try:
        # ========== 初始化所有数据库表 ==========
        init_users()
        init_ratings()
        init_preferences()
        init_comments()
        init_movie_cache()
        init_pools()
        init_profiles()

        logged_in = get(StateKeys.LOGGED_IN, False)
        username = get(StateKeys.USERNAME, "")

        if not logged_in:
            auth_page()
        else:
            # ========== 顶部导航 ==========
            # 处理全局搜索（在页面顶部捕获搜索词）
            if st.query_params.get('q'):
                set(StateKeys.GLOBAL_SEARCH_QUERY, st.query_params.get('q'))
                # 清空 query_params，避免重复
                st.query_params.clear()
                # 自动切换到"电影分类"标签页
                set(StateKeys.TAB_SELECTION, "🎞️ 电影分类")

            col_logo, col_search, col_avatar = st.columns([7, 2, 1])
            with col_logo:
                st.markdown("<div class='brand-text'>🎬 CineMind | 捕捉帧间情绪，邂逅专属好片</div>", unsafe_allow_html=True)
            with col_search:
                # ---------- 优化1：搜索框功能 ----------
                # 使用两列实现输入框+按钮内联
                search_col1, search_col2 = st.columns([4, 1])
                with search_col1:
                    search_keyword = st.text_input(
                        "搜索电影",
                        placeholder="🔍 搜索电影、导演或类型...",
                        label_visibility="collapsed",
                        key="global_search",
                        value=...,
                        autocomplete="off"
                    )
                with search_col2:
                    search_clicked = st.button("🔍", key="search_btn", use_container_width=True)

                # 如果用户按回车（通过检测输入变化）或点击搜索按钮
                if search_keyword and (search_clicked or st.session_state.get('_search_triggered', False)):
                    set(StateKeys.GLOBAL_SEARCH_QUERY, search_keyword)
                    # 跳转到电影分类页面，并传递搜索词
                    st.query_params['q'] = search_keyword
                    set(StateKeys.TAB_SELECTION, "🎞️ 电影分类")
                    st.rerun()
                # 如果输入为空但点击搜索，不做任何事
                if search_clicked and not search_keyword:
                    st.toast("请输入搜索关键词", icon="ℹ️")

            with col_avatar:
                username = get(StateKeys.USERNAME, "用户")
                initial = username[0].upper() if username else "U"
                with st.popover(f"{initial}", use_container_width=False):
                    st.write(f"👤 用户：{username}")
                    if st.button("🚪 登出", use_container_width=True):
                        set(StateKeys.LOGGED_IN, False)
                        set(StateKeys.USERNAME, "")
                        set(StateKeys.GLOBAL_SEARCH_QUERY, "")
                        st.rerun()

            # ---------- 导航选项卡 ----------
            # 如果有搜索词，默认选中"电影分类"标签页
            tab_labels = ["🏠 首页", "🎞️ 电影分类", "🔥 热门电影", "✨ 个性推荐", "📊 评分历史"]

            tab_selection = get(StateKeys.TAB_SELECTION, "")
            if tab_selection:
                default_tab_index = tab_labels.index(tab_selection) if tab_selection in tab_labels else 0
            else:
                default_tab_index = 0

            tab_home, tab_categories, tab_hot, tab_personal, tab_history = st.tabs(tab_labels)

            # 如果设置了默认选中的标签页，通过 session_state 传递
            if get(StateKeys.TAB_SELECTION) == "🎞️ 电影分类":
                # 在 categories.show() 中会读取 st.query_params 或 session_state
                pass

            with tab_home:
                home.show()
            with tab_categories:
                # 将搜索词传递给 categories 页面
                if get(StateKeys.GLOBAL_SEARCH_QUERY):
                    # 通过 session_state 传递搜索词，categories.show() 会读取
                    set(StateKeys.CATEGORIES_SEARCH_QUERY, get(StateKeys.GLOBAL_SEARCH_QUERY))
                categories.show()
            with tab_hot:
                hot.show()
            with tab_personal:
                personal.show()
            with tab_history:
                history.show()

            # 页脚
            st.markdown("<footer>CineMind · 多模态RAG智能推荐 | 每一部推荐均融合视觉、文本协同检索</footer>",
                        unsafe_allow_html=True)

            # 浮动对话窗口
            fp = FloatingContainer(
                icon=":material/chat:",
                label="CineMind 助手",
                start_position="bottom",
                key="chat_panel",
                glassmorphic=True,
                width="550px",
            )
            with fp.panel():
                show_floating_chat()

    except Exception as e:
        logger.error(f"应用运行失败: {e}")
        logger.error(traceback.format_exc())
        show_error_page(
            title="😱 哎呀，出错了",
            message="应用遇到了意外错误，请检查日志或联系管理员。"
        )


if __name__ == "__main__":
    main()