import streamlit as st

from qa_engine.app_state import require_current_session
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection

st.title("2. 列選択")
st.info("仮実装: AI連携前のため、全列を提案扱いにしています。")

conn = get_streamlit_connection()
session_id = require_current_session()

headers = repository.get_headers(conn, session_id)
already_confirmed = any(h["user_selected"] for h in headers)

with st.form("column_selection"):
    selected = []
    for h in headers:
        default = bool(h["user_selected"]) if already_confirmed else bool(h["ai_suggested"])
        label = h["column_name"] + ("(AI提案)" if h["ai_suggested"] else "")
        if st.checkbox(label, value=default, key=f"col_{session_id}_{h['column_name']}"):
            selected.append(h["column_name"])
    submitted = st.form_submit_button("確定", type="primary")

if submitted:
    if not selected:
        st.error("1列以上選択してください。")
    else:
        repository.update_column_selection(conn, session_id, selected)
        repository.update_session_status(conn, session_id, "columns_selected")
        st.success(f"確定しました: {', '.join(selected)}")
