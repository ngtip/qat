import streamlit as st

from qa_engine.config import load_settings
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.sidebar import render_sidebar

st.set_page_config(page_title="品質分析ツール", layout="wide")

get_streamlit_connection()
render_sidebar()

st.title("品質分析ツール")
st.write(
    "左のメニューから、取込 → 列選択 → 行チェック → ワードマイニング/重み付け → "
    "分析結果 の順に進めてください。"
)
st.markdown(
    "- **AIの呼び先**はサイドバーで切り替えます。開発・検証中は「手動中継」で、IDEのAIチャットにプロンプトを貼って実行します。\n"
    "- AIとのやり取りはすべてDBに記録され、分析結果の「AI処理ログ」とExcelレポートで確認できます。"
)
st.caption(f"DB: {load_settings().db_path}")
