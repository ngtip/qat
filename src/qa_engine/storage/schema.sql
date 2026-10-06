-- セッション(1回の取込〜分析のまとまり)。中長期分析はこのテーブルを跨いで集計する想定。
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_name TEXT,
    status TEXT NOT NULL DEFAULT 'ingesting'  -- ingesting / columns_selected / checked / scored / done
);

-- ヘッダ検出・列選択結果
CREATE TABLE IF NOT EXISTS session_headers (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    column_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    detected_type TEXT,  -- 列の役割(qa_engine.ai.base.ROLES のキー)
    ai_suggested INTEGER NOT NULL DEFAULT 0,
    ai_reason TEXT,
    user_selected INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, column_name)
);

-- 取込生データ(行単位、汎用にJSON格納)
CREATE TABLE IF NOT EXISTS session_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    row_index INTEGER NOT NULL,
    raw_data TEXT NOT NULL
);

-- 行別チェック結果
CREATE TABLE IF NOT EXISTS check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    row_id INTEGER NOT NULL REFERENCES session_rows(id),
    check_name TEXT NOT NULL,
    result TEXT NOT NULL,  -- JSON文字列(スコア・詳細等)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ワードマイニング結果とユーザーの重み付け
CREATE TABLE IF NOT EXISTS word_mining_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    term TEXT NOT NULL,
    frequency INTEGER,
    ai_score REAL,
    category TEXT,
    user_weight REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- AIとのやり取りの記録(どのデータをどの呼び先に送ったかを追跡する)。
-- 取込確定前のヘッダ検出は session_id が NULL のまま記録し、確定時に紐付ける。
CREATE TABLE IF NOT EXISTS ai_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    step TEXT NOT NULL,
    provider TEXT NOT NULL,
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 最終スコアリング結果(row_idがNULLならセッション全体スコア)
CREATE TABLE IF NOT EXISTS quality_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    row_id INTEGER REFERENCES session_rows(id),
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
