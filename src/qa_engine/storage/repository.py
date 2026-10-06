"""sessions以下の各テーブルへのCRUDをまとめる場所。pages側は原則ここ経由でDBに触る。"""

import json
import sqlite3


def create_session(conn: sqlite3.Connection, source_name: str) -> int:
    cur = conn.execute("INSERT INTO sessions (source_name) VALUES (?)", (source_name,))
    conn.commit()
    return cur.lastrowid


def update_session_status(conn: sqlite3.Connection, session_id: int, status: str) -> None:
    conn.execute("UPDATE sessions SET status = ? WHERE id = ?", (status, session_id))
    conn.commit()


def save_headers(conn: sqlite3.Connection, session_id: int, columns: list[str]) -> None:
    for position, col in enumerate(columns):
        conn.execute(
            "INSERT OR REPLACE INTO session_headers "
            "(session_id, column_name, position, ai_suggested, user_selected) "
            "VALUES (?, ?, ?, 0, 0)",
            (session_id, col, position),
        )
    conn.commit()


def save_column_suggestions(
    conn: sqlite3.Connection, session_id: int, suggestions: list, roles: dict[str, str]
) -> None:
    """AI(または簡易判定)の提案と、ユーザーが確定した役割を保存する。"""
    for s in suggestions:
        conn.execute(
            "UPDATE session_headers SET detected_type = ?, ai_suggested = ?, ai_reason = ? "
            "WHERE session_id = ? AND column_name = ?",
            (roles.get(s.column_name, s.role), int(s.recommended), s.reason, session_id, s.column_name),
        )
    conn.commit()


def get_column_roles(conn: sqlite3.Connection, session_id: int) -> dict[str, str]:
    rows = conn.execute(
        "SELECT column_name, detected_type FROM session_headers WHERE session_id = ? ORDER BY position",
        (session_id,),
    ).fetchall()
    return {r["column_name"]: r["detected_type"] or "other" for r in rows}


def get_headers(conn: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM session_headers WHERE session_id = ? ORDER BY position",
        (session_id,),
    ).fetchall()


def update_column_selection(
    conn: sqlite3.Connection, session_id: int, selected_columns: list[str]
) -> None:
    conn.execute("UPDATE session_headers SET user_selected = 0 WHERE session_id = ?", (session_id,))
    for col in selected_columns:
        conn.execute(
            "UPDATE session_headers SET user_selected = 1 WHERE session_id = ? AND column_name = ?",
            (session_id, col),
        )
    conn.commit()


def get_selected_columns(conn: sqlite3.Connection, session_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT column_name FROM session_headers "
        "WHERE session_id = ? AND user_selected = 1 ORDER BY position",
        (session_id,),
    ).fetchall()
    return [r["column_name"] for r in rows]


def save_rows(conn: sqlite3.Connection, session_id: int, rows: list[dict]) -> None:
    for i, row in enumerate(rows):
        conn.execute(
            "INSERT INTO session_rows (session_id, row_index, raw_data) VALUES (?, ?, ?)",
            (session_id, i, json.dumps(row, ensure_ascii=False)),
        )
    conn.commit()


def get_rows(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, row_index, raw_data FROM session_rows WHERE session_id = ? ORDER BY row_index",
        (session_id,),
    ).fetchall()
    result = []
    for r in rows:
        data = json.loads(r["raw_data"])
        result.append({"id": r["id"], "row_index": r["row_index"], **data})
    return result


def save_check_results(
    conn: sqlite3.Connection,
    session_id: int,
    check_name: str,
    results: list[tuple[int, dict]],
) -> None:
    """results: (row_id, detail) のリスト。"""
    for row_id, detail in results:
        conn.execute(
            "INSERT INTO check_results (session_id, row_id, check_name, result) VALUES (?, ?, ?, ?)",
            (session_id, row_id, check_name, json.dumps(detail, ensure_ascii=False)),
        )
    conn.commit()


def get_check_results(
    conn: sqlite3.Connection, session_id: int, check_name: str | None = None
) -> list[dict]:
    if check_name:
        rows = conn.execute(
            "SELECT * FROM check_results WHERE session_id = ? AND check_name = ?",
            (session_id, check_name),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM check_results WHERE session_id = ?", (session_id,)
        ).fetchall()
    return [
        {"row_id": r["row_id"], "check_name": r["check_name"], **json.loads(r["result"])}
        for r in rows
    ]


def clear_check_results(conn: sqlite3.Connection, session_id: int, check_name: str) -> None:
    conn.execute(
        "DELETE FROM check_results WHERE session_id = ? AND check_name = ?",
        (session_id, check_name),
    )
    conn.commit()


def save_word_mining_results(
    conn: sqlite3.Connection, session_id: int, results: list[dict]
) -> None:
    for r in results:
        conn.execute(
            "INSERT INTO word_mining_results "
            "(session_id, term, frequency, ai_score, category, user_weight) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, r["term"], r["frequency"], r["ai_score"], r.get("category"), r.get("user_weight")),
        )
    conn.commit()


def get_word_mining_results(conn: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM word_mining_results WHERE session_id = ? ORDER BY ai_score DESC, frequency DESC",
        (session_id,),
    ).fetchall()


def update_word_weight(
    conn: sqlite3.Connection, session_id: int, term: str, weight: float
) -> None:
    conn.execute(
        "UPDATE word_mining_results SET user_weight = ? WHERE session_id = ? AND term = ?",
        (weight, session_id, term),
    )
    conn.commit()


def clear_word_mining_results(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute("DELETE FROM word_mining_results WHERE session_id = ?", (session_id,))
    conn.commit()


def save_quality_scores(conn: sqlite3.Connection, session_id: int, scores: list[dict]) -> None:
    for s in scores:
        conn.execute(
            "INSERT INTO quality_scores (session_id, row_id, metric_name, value, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                s.get("row_id"),
                s["metric_name"],
                s["value"],
                json.dumps(s.get("detail"), ensure_ascii=False) if s.get("detail") else None,
            ),
        )
    conn.commit()


def get_quality_scores(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM quality_scores WHERE session_id = ?", (session_id,)
    ).fetchall()
    return [
        {
            "row_id": r["row_id"],
            "metric_name": r["metric_name"],
            "value": r["value"],
            "detail": json.loads(r["detail"]) if r["detail"] else None,
        }
        for r in rows
    ]


def clear_quality_scores(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute("DELETE FROM quality_scores WHERE session_id = ?", (session_id,))
    conn.commit()


def log_ai_interaction(
    conn: sqlite3.Connection,
    session_id: int | None,
    step: str,
    provider: str,
    prompt: str,
    response: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO ai_interactions (session_id, step, provider, prompt, response) VALUES (?, ?, ?, ?, ?)",
        (session_id, step, provider, prompt, response),
    )
    conn.commit()
    return cur.lastrowid


def bind_ai_interaction(conn: sqlite3.Connection, interaction_id: int, session_id: int) -> None:
    conn.execute(
        "UPDATE ai_interactions SET session_id = ? WHERE id = ? AND session_id IS NULL",
        (session_id, interaction_id),
    )
    conn.commit()


def get_ai_interactions(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM ai_interactions WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()
    return [dict(r) for r in rows]
