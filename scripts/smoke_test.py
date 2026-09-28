"""UIを介さずに 取込→列選択→行チェック→ワードマイニング→スコア の全工程を一時DBで通す。

成功時は "SMOKE TEST OK" を出力して終了コード0、失敗時は例外で非0終了。
"""

import py_compile
import sys
import tempfile
from pathlib import Path

import pandas as pd

from qa_engine.analysis.qualitative import naive_mine_words, weighted_average
from qa_engine.analysis.quantitative import duplicate_ratio
from qa_engine.analysis.scoring import naive_calculate_scores
from qa_engine.checks.duplicate_check import DuplicateCheck
from qa_engine.ingestion.header_detector import HeaderNotFoundError
from qa_engine.ingestion.naive_parser import parse_free_text
from qa_engine.report.formatter import format_scores_for_display
from qa_engine.storage import repository as repo
from qa_engine.storage.db import get_connection, init_db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    for page in [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py"))]:
        py_compile.compile(str(page), doraise=True)

    for bad in ["", "ヘッダの無い文章\n2行目", "A,A\n1,2"]:
        try:
            parse_free_text(bad)
        except HeaderNotFoundError:
            pass
        else:
            raise AssertionError(f"ヘッダ無し入力が受理された: {bad!r}")

    raw = (ROOT / "data" / "samples" / "sample_defects.csv").read_text(encoding="utf-8")
    header, rows = parse_free_text(raw)
    assert header == ["ID", "発生日", "工程", "不具合内容", "重要度"], header
    assert len(rows) == 8, len(rows)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "smoke.sqlite3")
        init_db(db_path)
        conn = get_connection(db_path)
        try:
            sid = repo.create_session(conn, "smoke")
            repo.save_headers(conn, sid, header)
            repo.save_rows(conn, sid, rows)
            assert [h["column_name"] for h in repo.get_headers(conn, sid)] == header

            repo.update_column_selection(conn, sid, ["不具合内容", "工程"])
            columns = repo.get_selected_columns(conn, sid)
            assert columns == ["工程", "不具合内容"], columns

            stored_rows = repo.get_rows(conn, sid)
            check = DuplicateCheck(similarity_threshold=90)
            results = check.run(pd.DataFrame(stored_rows), columns)
            repo.save_check_results(
                conn, sid, check.name,
                [(stored_rows[r.row_index]["id"], r.detail) for r in results],
            )
            check_results = repo.get_check_results(conn, sid, check.name)
            flagged = sum(1 for r in check_results if r["duplicate_matches"])
            assert flagged == 4, flagged

            words = naive_mine_words([" ".join(r[c] for c in columns) for r in stored_rows])
            repo.save_word_mining_results(
                conn, sid,
                [{"term": w.term, "frequency": w.frequency, "ai_score": w.ai_score} for w in words],
            )
            repo.update_word_weight(conn, sid, "組立", 1.0)
            saved_words = repo.get_word_mining_results(conn, sid)
            assert saved_words[0]["term"] == "組立" and saved_words[0]["frequency"] == 3

            word_avg = weighted_average(
                [w["frequency"] for w in saved_words],
                [w["user_weight"] if w["user_weight"] is not None else 0.5 for w in saved_words],
            )
            scores = naive_calculate_scores(duplicate_ratio(check_results, len(stored_rows)), word_avg)
            repo.save_quality_scores(conn, sid, scores)
            display = format_scores_for_display(repo.get_quality_scores(conn, sid))
            assert len(display) == 3, display
        finally:
            conn.close()

    print("SMOKE TEST OK")
    for item in display:
        print(item)


if __name__ == "__main__":
    main()
    sys.exit(0)
