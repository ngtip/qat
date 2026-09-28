import pandas as pd
import streamlit as st

from qa_engine.app_state import require_current_session
from qa_engine.checks.duplicate_check import DuplicateCheck
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection

st.title("3. 行チェック")

conn = get_streamlit_connection()
session_id = require_current_session()

columns = repository.get_selected_columns(conn, session_id)
if not columns:
    st.warning("先に「2. 列選択」で列を確定してください。")
    st.stop()

st.write(f"対象列: {', '.join(columns)}")
threshold = st.slider("重複とみなす類似度(%)", 50, 100, 90)

if st.button("重複チェック実行", type="primary"):
    rows = repository.get_rows(conn, session_id)
    df = pd.DataFrame(rows)
    check = DuplicateCheck(similarity_threshold=threshold)
    results = check.run(df, columns)

    repository.clear_check_results(conn, session_id, check.name)
    repository.save_check_results(
        conn, session_id, check.name, [(rows[r.row_index]["id"], r.detail) for r in results]
    )
    repository.update_session_status(conn, session_id, "checked")

saved = repository.get_check_results(conn, session_id, DuplicateCheck.name)
if saved:
    rows_by_id = {r["id"]: r for r in repository.get_rows(conn, session_id)}
    table = [
        {
            "行": rows_by_id[r["row_id"]]["row_index"],
            **{c: rows_by_id[r["row_id"]].get(c, "") for c in columns},
            "重複候補(行)": ", ".join(str(m["row_index"]) for m in r["duplicate_matches"]),
            "最大類似度": max((m["similarity"] for m in r["duplicate_matches"]), default=None),
        }
        for r in saved
    ]
    flagged = sum(1 for r in saved if r["duplicate_matches"])
    st.metric("重複候補がある行", f"{flagged} / {len(saved)}")
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
