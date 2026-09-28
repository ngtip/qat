import pandas as pd
import streamlit as st

from qa_engine.app_state import set_current_session
from qa_engine.ingestion.header_detector import HeaderNotFoundError
from qa_engine.ingestion.naive_parser import parse_free_text
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection

st.title("1. 取込")
st.info("仮実装: AI連携前のため、1行目をヘッダとするCSV/TSVとして解析しています。")

conn = get_streamlit_connection()

uploaded = st.file_uploader("ファイルを選択", type=["csv", "tsv", "txt"])
pasted = st.text_area("またはテキストを貼り付け", height=200)

if st.button("取込実行", type="primary"):
    if uploaded is not None:
        raw_text = uploaded.getvalue().decode("utf-8-sig")
        source_name = uploaded.name
    else:
        raw_text = pasted
        source_name = "貼り付け"

    try:
        header, rows = parse_free_text(raw_text)
    except HeaderNotFoundError as e:
        st.error(f"取込できません: {e}")
        st.stop()

    session_id = repository.create_session(conn, source_name)
    repository.save_headers(conn, session_id, header)
    repository.save_rows(conn, session_id, rows)
    set_current_session(session_id)

    st.success(f"セッション {session_id} を作成しました({len(header)}列 / {len(rows)}行)")
    st.dataframe(pd.DataFrame(rows, columns=header), use_container_width=True)
