import streamlit as st

from qa_engine.ai.base import ROLES
from qa_engine.ai.tasks import COLUMN_SUGGESTION
from qa_engine.app_state import require_current_session
from qa_engine.ingestion.column_suggester import suggest_columns_naive
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.ai_step import run_ai_step
from qa_engine.ui.sidebar import render_sidebar

SAMPLE_ROWS = 5

st.title("2. 列選択")
render_sidebar()
conn = get_streamlit_connection()
session_id = require_current_session()

headers = {h["column_name"]: h for h in repository.get_headers(conn, session_id)}
columns = list(headers)
rows = [{c: r.get(c, "") for c in columns} for r in repository.get_rows(conn, session_id)]

st.subheader("列提案")
outcome = run_ai_step(
    f"column_suggestion::{session_id}",
    COLUMN_SUGGESTION,
    {"columns": columns, "sample_rows": rows[:SAMPLE_ROWS]},
    naive_fn=lambda: suggest_columns_naive(columns, rows),
    session_id=session_id,
)
if outcome is None:
    st.stop()

confirmed = any(h["user_selected"] for h in headers.values())
role_keys = list(ROLES)

with st.form("column_selection"):
    st.write("分析に使う列にチェックを入れ、必要なら役割を直してください。")
    selected, roles = [], {}
    for s in outcome.value:
        h = headers[s.column_name]
        left, mid, right = st.columns([3, 2, 5])
        checked = bool(h["user_selected"]) if confirmed else s.recommended
        if left.checkbox(s.column_name, value=checked, key=f"col_{session_id}_{s.column_name}"):
            selected.append(s.column_name)
        role = h["detected_type"] if confirmed and h["detected_type"] in ROLES else s.role
        roles[s.column_name] = mid.selectbox(
            "役割", role_keys, index=role_keys.index(role), format_func=ROLES.get,
            key=f"role_{session_id}_{s.column_name}", label_visibility="collapsed",
        )
        right.caption(("推奨 ・ " if s.recommended else "") + s.reason)
    submitted = st.form_submit_button("確定", type="primary")

if submitted:
    if not selected:
        st.error("1列以上選択してください。")
    else:
        repository.save_column_suggestions(conn, session_id, outcome.value, roles)
        repository.update_column_selection(conn, session_id, selected)
        repository.update_session_status(conn, session_id, "columns_selected")
        st.success(f"確定しました: {', '.join(selected)}")
