# utils/error_handling.py
"""
统一错误处理
"""
import streamlit as st
import traceback
import sys
from functools import wraps
from utils.logger import get_logger

logger = get_logger("error_handling")


def handle_error(func):
    """
    装饰器：统一捕获函数中的异常
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"函数 {func.__name__} 执行失败: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            st.error(f"❌ 操作失败：{str(e)[:100]}")
            return None

    return wrapper


def show_error_page(title: str = "出错了", message: str = "抱歉，发生了意外错误"):
    """显示错误页面"""
    st.error(f"### {title}")
    st.write(message)
    st.write("请尝试刷新页面或联系管理员。")
    if st.button("🔄 返回首页"):
        st.switch_page("app.py")


def log_and_show_error(e: Exception, context: str = ""):
    """
    记录错误并显示友好的错误信息

    Args:
        e: 异常对象
        context: 上下文描述
    """
    error_msg = f"{context}: {str(e)}" if context else str(e)
    logger.error(error_msg)
    logger.error(traceback.format_exc())
    st.error(f"❌ {error_msg[:150]}")