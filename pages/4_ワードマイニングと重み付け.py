import streamlit as st

from qa_engine.analysis.qualitative import naive_mine_words
from qa_engine.app_state import require_current_session
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection

st.title("4. ワードマイニングと重み付け")
st.info("仮実装: AI連携前のため、文字種区切りの頻度集計で代用しています。")

conn = get_streamlit_connection()
session_id = require_current_session()

columns = repository.get_selected_columns(conn, session_id)
if not columns:
    st.warning("先に「2. 列選択」で列を確定してください。")
    st.stop()

if st.button("ワードマイニング実行", type="primary"):
    rows = repository.get_rows(conn, session_id)
    texts = [" ".join(str(r.get(c, "")) for c in columns) for r in rows]
    results = naive_mine_words(texts)
    repository.clear_word_mining_results(conn, session_id)
    repository.save_word_mining_results(
        conn,
        session_id,
        [{"term": r.term, "frequency": r.frequency, "ai_score": r.ai_score} for r in results],
    )

words = repository.get_word_mining_results(conn, session_id)
if words:
    st.subheader("重み付け(0 = 無視 / 1 = 最重視)")
    with st.form("weights"):
        weights = {}
        for w in words:
            default = w["user_weight"] if w["user_weight"] is not None else 0.5
            weights[w["term"]] = st.slider(
                f"{w['term']}(出現 {w['frequency']} 回 / AIスコア {w['ai_score']})",
                0.0,
                1.0,
                float(default),
                0.1,
                key=f"w_{session_id}_{w['term']}",
            )
        if st.form_submit_button("重みを保存", type="primary"):
            for term, weight in weights.items():
                repository.update_word_weight(conn, session_id, term, weight)
            st.success("保存しました")
