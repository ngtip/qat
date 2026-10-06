import pandas as pd
import streamlit as st

from qa_engine.ai.tasks import HEAD_LINE_LIMIT, HEADER_DETECTION
from qa_engine.app_state import set_current_session
from qa_engine.ingestion.header_detector import HeaderNotFoundError, detect_header_naive
from qa_engine.ingestion.parser import parse_with_header
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.ai_step import run_ai_step
from qa_engine.ui.sidebar import render_sidebar


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp932")


st.title("1. 取込")
render_sidebar()
conn = get_streamlit_connection()

uploaded = st.file_uploader("ファイルを選択(CSV / TSV / テキスト)", type=["csv", "tsv", "txt"])
pasted = st.text_area("またはテキストを貼り付け(Excelからのコピーも可)", height=150)

if uploaded is not None:
    raw_text, source_name = _decode(uploaded.getvalue()), uploaded.name
else:
    raw_text, source_name = pasted, "貼り付け"
if not raw_text.strip():
    st.stop()

st.subheader("ヘッダ検出")
outcome = run_ai_step(
    "header_detection",
    HEADER_DETECTION,
    {"head_lines": raw_text.splitlines()[:HEAD_LINE_LIMIT]},
    naive_fn=lambda: detect_header_naive(raw_text),
)
if outcome is None:
    st.stop()

try:
    header, rows = parse_with_header(raw_text, outcome.value)
except HeaderNotFoundError as e:
    st.error(f"取込できません: {e}")
    st.stop()

st.success(
    f"{outcome.value.header_row_index + 1}行目をヘッダとして検出しました({len(header)}列 / {len(rows)}行)"
)
st.dataframe(pd.DataFrame(rows, columns=header), width="stretch", height=300)

if st.button("この内容で取込を確定", type="primary"):
    session_id = repository.create_session(conn, source_name)
    repository.save_headers(conn, session_id, header)
    repository.save_rows(conn, session_id, rows)
    if outcome.interaction_id:
        repository.bind_ai_interaction(conn, outcome.interaction_id, session_id)
    set_current_session(session_id)
    st.success(f"セッション {session_id} を作成しました。サイドバーの「列選択」へ進んでください。")
