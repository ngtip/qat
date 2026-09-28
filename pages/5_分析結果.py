import json

import pandas as pd
import streamlit as st

from qa_engine.analysis.qualitative import weighted_average
from qa_engine.analysis.quantitative import duplicate_ratio
from qa_engine.analysis.scoring import naive_calculate_scores
from qa_engine.app_state import require_current_session
from qa_engine.checks.duplicate_check import DuplicateCheck
from qa_engine.report.formatter import format_scores_for_display
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection

st.title("5. 分析結果")
st.info("仮実装: スコアの合成式は暫定です。")

conn = get_streamlit_connection()
session_id = require_current_session()

check_results = repository.get_check_results(conn, session_id, DuplicateCheck.name)
words = repository.get_word_mining_results(conn, session_id)
if not check_results or not words:
    st.warning("先に「3. 行チェック」と「4. ワードマイニングと重み付け」を実行してください。")
    st.stop()

if st.button("分析実行", type="primary"):
    total_rows = len(repository.get_rows(conn, session_id))
    dup = duplicate_ratio(check_results, total_rows)
    word_avg = weighted_average(
        [w["frequency"] for w in words],
        [w["user_weight"] if w["user_weight"] is not None else 0.5 for w in words],
    )
    repository.clear_quality_scores(conn, session_id)
    repository.save_quality_scores(conn, session_id, naive_calculate_scores(dup, word_avg))
    repository.update_session_status(conn, session_id, "done")

scores = repository.get_quality_scores(conn, session_id)
if scores:
    display = format_scores_for_display(scores)
    st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
    st.download_button(
        "結果をJSONでダウンロード",
        json.dumps({"session_id": session_id, "scores": scores}, ensure_ascii=False, indent=2),
        file_name=f"quality_scores_session{session_id}.json",
        mime="application/json",
    )
