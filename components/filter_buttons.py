# components/filter_buttons.py
"""
筛选按钮组件
"""
import streamlit as st


def render_filter_buttons(items, session_key, active_key=None, columns=3):
    """
    渲染筛选按钮组

    Args:
        items: list of (label, value) 或 list of strings
        session_key: session_state 中存储选中项的 key
        active_key: 用于标识"全部"的键值
        columns: 每行按钮数
    """
    if items and isinstance(items[0], str):
        items = [(item, item) for item in items]

    for i in range(0, len(items), columns):
        cols = st.columns(columns)
        for j, col in enumerate(cols):
            if i + j < len(items):
                label, value = items[i + j]
                is_active = (value == st.session_state.get(session_key))

                with col:
                    if st.button(
                            label,
                            key=f"{session_key}_{value}",
                            use_container_width=True,
                            type="primary" if is_active else "secondary"
                    ):
                        if active_key and value == active_key:
                            st.session_state[session_key] = None
                        else:
                            st.session_state[session_key] = value
                        st.rerun()