"""UIを介さずに全工程を一時DBで通す疎通確認。

- AIを使わない簡易ロジックで、取込 → 列提案 → 重複チェック → ワードマイニング → レポート → Excel まで通す
- 手動中継の応答パーサを tests/fixtures/ の固定応答で検証する(固定応答は検証専用)

成功時は "SMOKE TEST OK" を出力して終了コード0、失敗時は例外で非0終了。
"""

import io
import py_compile
import tempfile
from pathlib import Path

import pandas as pd

from qa_engine.ai.tasks import (
    COLUMN_SUGGESTION,
    HEAD_LINE_LIMIT,
    HEADER_DETECTION,
    WORD_MINING,
    AIResponseError,
)
from qa_engine.analysis.qualitative import naive_mine_words
from qa_engine.checks.duplicate_check import DuplicateCheck
from qa_engine.ingestion.column_suggester import suggest_columns_naive
from qa_engine.ingestion.header_detector import HeaderNotFoundError, detect_header_naive
from qa_engine.ingestion.parser import parse_with_header
from qa_engine.report.builder import build_report
from qa_engine.report.excel_export import to_excel_bytes
from qa_engine.storage import repository as repo
from qa_engine.storage.db import get_connection, init_db

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
DEMO_CSV = ROOT / "data" / "samples" / "bug_tickets_demo.csv"
EXPECTED_COLUMNS = [
    "障害ID", "起票日", "発見工程", "機能", "重要度", "現象",
    "原因区分", "原因詳細", "対策", "担当者", "ステータス", "対応工数h",
]
EXPECTED_SHEETS = [
    "サマリ", "分類別件数", "重要度クロス", "週次推移", "要注意度",
    "要注目障害", "重複候補", "重要語と重み", "AI処理ログ",
]


def expect_error(error_type: type[Exception], fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except error_type:
        return
    raise AssertionError(f"{error_type.__name__} が送出されなかった: {fn.__name__}{args}")


def check_ingestion(raw: str) -> tuple[list[str], list[dict]]:
    header_info = detect_header_naive(raw)
    assert header_info.header_row_index == 2, header_info
    header, rows = parse_with_header(raw, header_info)
    assert header == EXPECTED_COLUMNS, header
    assert len(rows) == 80, len(rows)

    for bad in ["", "ヘッダの無い文章\n2行目も文章"]:
        expect_error(HeaderNotFoundError, detect_header_naive, bad)
    expect_error(HeaderNotFoundError, parse_with_header, "A,A\n1,2", detect_header_naive("A,A\n1,2"))
    return header, rows


def check_relay_parsers(raw: str, header: list[str], rows: list[dict]) -> tuple[list, list]:
    head_lines = raw.splitlines()[:HEAD_LINE_LIMIT]
    relay_header = HEADER_DETECTION.parse_response((FIXTURES / "header_response.txt").read_text(encoding="utf-8"))
    assert parse_with_header(raw, relay_header) == (header, rows)
    expect_error(HeaderNotFoundError, HEADER_DETECTION.parse_response, '{"error": "no_header"}')
    expect_error(AIResponseError, HEADER_DETECTION.parse_response, "すみません、分かりません。")

    suggestions = COLUMN_SUGGESTION.parse_response(
        (FIXTURES / "column_response.json").read_text(encoding="utf-8"), columns=header
    )
    assert [s.column_name for s in suggestions] == header
    assert {s.column_name: s.role for s in suggestions}["重要度"] == "severity"

    texts = [" / ".join(r[c] for c in ("現象", "原因詳細") if r[c]) for r in rows]
    words = WORD_MINING.parse_response(
        (FIXTURES / "word_mining_response.txt").read_text(encoding="utf-8"), texts=texts
    )
    terms = {w.term: w for w in words}
    assert "本文に無い語" not in terms, "本文に無い語は除外されるべき"
    assert terms["テスト"].ai_score == 1.0 and terms["テスト"].category == "その他"
    assert all(w.frequency > 0 for w in words)

    prompt_sizes = {
        "ヘッダ検出": len(HEADER_DETECTION.build_prompt(head_lines=head_lines)),
        "列提案": len(COLUMN_SUGGESTION.build_prompt(columns=header, sample_rows=rows[:5])),
        "ワードマイニング": len(WORD_MINING.build_prompt(texts=texts)),
    }
    print("プロンプトの文字数:", prompt_sizes)
    return suggestions, words


def check_pipeline(header: list[str], rows: list[dict], relay_words: list) -> dict[str, pd.DataFrame]:
    naive_suggestions = suggest_columns_naive(header, rows)
    naive_roles = {s.column_name: s.role for s in naive_suggestions}
    assert naive_roles["起票日"] == "date" and naive_roles["重要度"] == "severity"
    assert naive_roles["現象"] == "free_text" and naive_roles["障害ID"] == "id"

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "smoke.sqlite3")
        init_db(db_path)
        conn = get_connection(db_path)
        try:
            sid = repo.create_session(conn, "smoke")
            repo.save_headers(conn, sid, header)
            repo.save_rows(conn, sid, rows)
            log_id = repo.log_ai_interaction(conn, None, "header_detection", "manual_relay", "p", "r")
            repo.bind_ai_interaction(conn, log_id, sid)

            roles = {s.column_name: s.role for s in naive_suggestions}
            repo.save_column_suggestions(conn, sid, naive_suggestions, roles)
            repo.update_column_selection(conn, sid, [s.column_name for s in naive_suggestions if s.recommended])
            selected = repo.get_selected_columns(conn, sid)
            roles = repo.get_column_roles(conn, sid)
            targets = [c for c in selected if roles[c] == "free_text"]

            stored = repo.get_rows(conn, sid)
            check = DuplicateCheck(similarity_threshold=75)
            results = check.run(pd.DataFrame(stored), ["現象"])
            repo.save_check_results(conn, sid, check.name, [(stored[r.row_index]["id"], r.detail) for r in results])

            naive_words = naive_mine_words([" ".join(r[c] for c in targets) for r in stored])
            assert naive_words, "簡易ワードマイニングの結果が空"
            repo.save_word_mining_results(conn, sid, [
                {"term": w.term, "frequency": w.frequency, "ai_score": w.ai_score,
                 "category": w.category, "user_weight": w.ai_score}
                for w in relay_words
            ])

            report = build_report(
                stored, roles, selected,
                repo.get_check_results(conn, sid, check.name),
                [dict(w) for w in repo.get_word_mining_results(conn, sid)],
                repo.get_ai_interactions(conn, sid),
                ranking_col="機能",
            )
            repo.save_quality_scores(conn, sid, report.scores)
            assert len(repo.get_ai_interactions(conn, sid)) == 1
        finally:
            conn.close()

    assert report.ranking is not None and len(report.ranking) == 8, report.ranking
    assert len(report.duplicates) == 12, f"重複候補の行数が想定外: {len(report.duplicates)}"
    assert not report.attention.empty, "要注目障害が1件も無い"
    for label, value in report.kpis:
        print(f"  {label}: {value}")

    sheets = pd.read_excel(io.BytesIO(to_excel_bytes(report.sheets())), sheet_name=None)
    assert list(sheets) == EXPECTED_SHEETS, list(sheets)
    return sheets


def main() -> None:
    for page in [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py"))]:
        py_compile.compile(str(page), doraise=True)

    raw = DEMO_CSV.read_text(encoding="utf-8-sig")
    header, rows = check_ingestion(raw)
    _, relay_words = check_relay_parsers(raw, header, rows)
    sheets = check_pipeline(header, rows, relay_words)

    print("Excelのシート:", {name: len(frame) for name, frame in sheets.items()})
    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
