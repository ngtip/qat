import streamlit as st

from qa_engine.app_state import get_current_session
from qa_engine.config import load_settings
from qa_engine.storage.connection import get_streamlit_connection

st.set_page_config(page_title="品質分析ツール", layout="wide")

get_streamlit_connection()

st.title("品質分析ツール")
st.write(
    "左のメニューから、取込 → 列選択 → 行チェック → ワードマイニング/重み付け → "
    "分析結果 の順に進めてください。"
)

st.caption(f"DB: {load_settings().db_path}")
session_id = get_current_session()
st.caption(f"現在のセッション: {session_id if session_id else '未作成'}")
