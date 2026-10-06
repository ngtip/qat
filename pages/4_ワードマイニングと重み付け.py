import pandas as pd
import streamlit as st

from qa_engine.ai.tasks import WORD_MINING
from qa_engine.analysis.qualitative import naive_mine_words
from qa_engine.app_state import require_current_session
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.ai_step import run_ai_step
from qa_engine.ui.sidebar import render_sidebar

st.title("4. ワードマイニングと重み付け")
render_sidebar()
conn = get_streamlit_connection()
session_id = require_current_session()

selected = repository.get_selected_columns(conn, session_id)
if not selected:
    st.warning("先に「2. 列選択」で列を確定してください。")
    st.stop()

roles = repository.get_column_roles(conn, session_id)
text_cols = [c for c in selected if roles.get(c) == "free_text"] or selected
rows = repository.get_rows(conn, session_id)
texts = [" / ".join(str(r.get(c, "")) for c in text_cols if str(r.get(c, "")).strip()) for r in rows]

st.subheader("ワードマイニング")
st.caption(f"対象列: {', '.join(text_cols)}")
outcome = run_ai_step(
    f"word_mining::{session_id}",
    WORD_MINING,
    {"texts": texts},
    naive_fn=lambda: naive_mine_words(texts),
    session_id=session_id,
)
if outcome is None:
    st.stop()

st.dataframe(
    pd.DataFrame(
        [{"語句": w.term, "カテゴリ": w.category or "", "出現回数": w.frequency, "AI重要度": w.ai_score}
         for w in outcome.value]
    ),
    width="stretch",
    hide_index=True,
    height=250,
)
if st.button("この結果を保存して重み付けへ進む", type="primary"):
    repository.clear_word_mining_results(conn, session_id)
    repository.save_word_mining_results(
        conn,
        session_id,
        [
            {"term": w.term, "frequency": w.frequency, "ai_score": w.ai_score,
             "category": w.category, "user_weight": w.ai_score}
            for w in outcome.value
        ],
    )

words = repository.get_word_mining_results(conn, session_id)
if words:
    st.subheader("重み付け(0 = 無視 / 1 = 最重視)")
    st.caption("初期値はAIの重要度です。分析で重視したい語の重みを上げてください。")
    with st.form("weights"):
        weights = {}
        for w in words:
            weights[w["term"]] = st.slider(
                f"{w['term']}({w['category'] or '-'} / 出現 {w['frequency']} 回 / AI重要度 {w['ai_score']})",
                0.0, 1.0, float(w["user_weight"] if w["user_weight"] is not None else w["ai_score"]), 0.1,
                key=f"w_{session_id}_{w['term']}",
            )
        if st.form_submit_button("重みを保存", type="primary"):
            for term, weight in weights.items():
                repository.update_word_weight(conn, session_id, term, weight)
            st.success("保存しました。サイドバーの「分析結果」へ進んでください。")
