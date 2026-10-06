import streamlit as st

from qa_engine.app_state import require_current_session
from qa_engine.checks.duplicate_check import DuplicateCheck
from qa_engine.report.builder import NOTE, build_report
from qa_engine.report.excel_export import to_excel_bytes
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.sidebar import render_sidebar

st.title("5. 分析結果")
render_sidebar()
conn = get_streamlit_connection()
session_id = require_current_session()

selected = repository.get_selected_columns(conn, session_id)
check_results = repository.get_check_results(conn, session_id, DuplicateCheck.name)
words = [dict(w) for w in repository.get_word_mining_results(conn, session_id)]
if not selected or not check_results or not words:
    st.warning("先に「3. 行チェック」と「4. ワードマイニングと重み付け」を実行してください。")
    st.stop()

roles = repository.get_column_roles(conn, session_id)
category_cols = [c for c in selected if roles.get(c) == "category"]
ranking_col = (
    st.selectbox("要注意度を集計する分類", category_cols, index=category_cols.index("機能") if "機能" in category_cols else 0)
    if category_cols
    else None
)
report = build_report(
    repository.get_rows(conn, session_id),
    roles,
    selected,
    check_results,
    words,
    repository.get_ai_interactions(conn, session_id),
    ranking_col,
)
st.caption(NOTE)

for column, (label, value) in zip(st.columns(len(report.kpis)), report.kpis):
    column.metric(label, value)

tabs = st.tabs(["分類別", "推移", "要注意度", "要注目障害", "重複候補", "重要語", "AI処理ログ"])

with tabs[0]:
    if report.category_counts:
        column = st.selectbox("分類", list(report.category_counts), key="category_tab")
        st.bar_chart(report.category_counts[column], x=column, y="件数", horizontal=True, sort="-件数")
        if column in report.crosstabs:
            st.write("重要度とのクロス集計")
            st.dataframe(report.crosstabs[column], width="stretch", hide_index=True)
    else:
        st.info("役割が「分類」の列が選択されていません。")

with tabs[1]:
    if report.trend is not None and not report.trend.empty:
        series = [c for c in report.trend.columns if c not in ("週", "件数")] or ["件数"]
        st.bar_chart(report.trend, x="週", y=series, stack=True)
        st.dataframe(report.trend, width="stretch", hide_index=True)
    else:
        st.info("役割が「日付」の列が選択されていません。")

with tabs[2]:
    if report.ranking is not None:
        st.bar_chart(report.ranking, x=report.ranking_col, y="要注意度", horizontal=True, sort="-要注意度")
        st.dataframe(report.ranking, width="stretch", hide_index=True)
    else:
        st.info("役割が「分類」の列が選択されていません。")

with tabs[3]:
    st.caption("重大(重要度S/A相当)で、かつ重み0.7以上の語を含む障害")
    st.dataframe(report.attention, width="stretch", hide_index=True)

with tabs[4]:
    st.dataframe(report.duplicates, width="stretch", hide_index=True)

with tabs[5]:
    st.dataframe(report.words, width="stretch", hide_index=True)

with tabs[6]:
    if report.interactions.empty:
        st.info("このセッションではAIとのやり取りがありません(簡易ロジックで実行)。")
    for _, item in report.interactions.iterrows():
        with st.expander(f"{item['工程']} / {item['呼び先']} / {item['日時(UTC)']}"):
            st.write("送信したプロンプト")
            st.code(item["送信したプロンプト"], language="text", wrap_lines=True, height=200)
            st.write("AIの応答")
            st.code(item["AIの応答"], language="text", wrap_lines=True, height=200)

st.divider()
left, right = st.columns(2)
if left.button("分析結果をDBに記録", type="primary"):
    repository.clear_quality_scores(conn, session_id)
    repository.save_quality_scores(conn, session_id, report.scores)
    repository.update_session_status(conn, session_id, "done")
    left.success("記録しました(中長期分析用の蓄積)。")
right.download_button(
    "Excelレポートをダウンロード",
    to_excel_bytes(report.sheets()),
    file_name=f"品質分析レポート_session{session_id}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
