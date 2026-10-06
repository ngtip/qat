"""全ページ共通のサイドバー。AIの呼び先をここで切り替える(既定値は config.py / 環境変数 QA_AI_PROVIDER)。"""

import streamlit as st

from qa_engine.ai.providers import PROVIDER_LABELS
from qa_engine.app_state import get_current_session
from qa_engine.config import load_settings

_KEY = "qa_ai_provider_choice"


def current_provider() -> str:
    choice = st.session_state.get(_KEY, load_settings().ai_provider)
    return choice if choice in PROVIDER_LABELS else "manual_relay"


def render_sidebar() -> str:
    options = list(PROVIDER_LABELS)
    choice = st.sidebar.radio(
        "AIの呼び先",
        options,
        index=options.index(current_provider()),
        format_func=PROVIDER_LABELS.get,
        help="コンプラ要件に合わせて、AI処理の送り先を切り替えます。",
    )
    st.session_state[_KEY] = choice
    session_id = get_current_session()
    st.sidebar.caption(f"分析セッション: {session_id if session_id else '未作成'}")
    return choice
