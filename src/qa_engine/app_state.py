"""ページ間で共有する現在の分析セッションの状態管理。"""

import streamlit as st

_SESSION_KEY = "qa_session_id"


def set_current_session(session_id: int) -> None:
    st.session_state[_SESSION_KEY] = session_id


def get_current_session() -> int | None:
    return st.session_state.get(_SESSION_KEY)


def require_current_session() -> int:
    session_id = get_current_session()
    if session_id is None:
        st.warning("先に「1. 取込」でデータを取り込んでください。")
        st.stop()
    return session_id
