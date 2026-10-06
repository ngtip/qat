import pandas as pd
import streamlit as st

from qa_engine.app_state import require_current_session
from qa_engine.checks.duplicate_check import DuplicateCheck
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.sidebar import render_sidebar

st.title("3. 行チェック")
render_sidebar()
conn = get_streamlit_connection()
session_id = require_current_session()

selected = repository.get_selected_columns(conn, session_id)
if not selected:
    st.warning("先に「2. 列選択」で列を確定してください。")
    st.stop()

roles = repository.get_column_roles(conn, session_id)
text_cols = [c for c in selected if roles.get(c) == "free_text"]
id_col = next((c for c, r in roles.items() if r == "id"), None)

targets = st.multiselect(
    "重複チェックの対象列(同じ障害かどうかを判断する列)",
    selected,
    default=text_cols[:1] or selected[:1],
)
threshold = st.slider("重複とみなす類似度(%)", 50, 100, 75)
st.caption("文字列の近さ(Levenshtein距離)で判定します。言い回しが大きく違う重複は拾えません。")
if not targets:
    st.stop()

if st.button("重複チェック実行", type="primary"):
    rows = repository.get_rows(conn, session_id)
    check = DuplicateCheck(similarity_threshold=threshold)
    results = check.run(pd.DataFrame(rows), targets)
    repository.clear_check_results(conn, session_id, check.name)
    repository.save_check_results(
        conn, session_id, check.name, [(rows[r.row_index]["id"], r.detail) for r in results]
    )
    repository.update_session_status(conn, session_id, "checked")

saved = repository.get_check_results(conn, session_id, DuplicateCheck.name)
if saved:
    rows_by_id = {r["id"]: r for r in repository.get_rows(conn, session_id)}
    label_by_index = {r["row_index"]: (r.get(id_col) if id_col else r["row_index"]) for r in rows_by_id.values()}
    flagged = [r for r in saved if r["duplicate_matches"]]
    st.metric("重複候補がある行", f"{len(flagged)} / {len(saved)}")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": label_by_index[rows_by_id[r["row_id"]]["row_index"]],
                    **{c: rows_by_id[r["row_id"]].get(c, "") for c in targets},
                    "重複候補": "、".join(str(label_by_index[m["row_index"]]) for m in r["duplicate_matches"]),
                    "最大類似度": max(m["similarity"] for m in r["duplicate_matches"]),
                }
                for r in flagged
            ]
        ),
        width="stretch",
        hide_index=True,
    )
