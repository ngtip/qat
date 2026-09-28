# SETUP_FOR_AI

Audience: an AI coding agent (e.g. GitHub Copilot agent mode in VS Code) setting up this repository on a new Windows PC.
Goal: reproduce a working dev environment and confirm the app runs end-to-end. Human readability is not a goal.
Write replies to the user in Japanese.

## 0. Hard rules

- Target environment: company-managed Windows PC, VS Code, GitHub Copilot Business. Treat it as a restricted corporate machine.
- Do NOT install system-wide software (Python, Git, etc.), change system settings, edit the registry, or change the PowerShell execution policy. If a prerequisite is missing, STOP and tell the user what is missing.
- Do NOT bypass TLS/proxy errors (no `--trusted-host`, no `verify=False`, no `PIP_CERT` pointing to random files, no disabling SSL). On network/proxy/SSL failure, STOP and report the exact error to the user; they may need the company proxy or internal PyPI mirror settings.
- Install packages ONLY into the project-local venv at `.venv`. Never `pip install` into the global interpreter. Never use `--user`.
- Do NOT activate the venv via `Activate.ps1` (execution policy may block it). Always call `.\.venv\Scripts\python.exe` directly.
- Streamlit must bind to localhost only (`--server.address=localhost`) and must not send usage stats (`--browser.gatherUsageStats=false`). Do not expose the server on the network.
- Do not commit `.venv/`, `data/db/*.sqlite3`, `*.egg-info/`, `__pycache__/` (already in `.gitignore`).
- Ignore `.claude/` (config for a different tool; irrelevant to VS Code).
- Default shell: PowerShell in the VS Code integrated terminal. All commands below assume the working directory is the repository root.

## 1. Project facts (read before changing anything)

- Purpose: quality analysis tool. Free-format tabular input -> header detection -> column suggestion -> user column selection -> per-row checks -> quantitative + qualitative (word mining) analysis -> user weighting -> quality score output.
- Stack: Python 3.11+ (developed/tested on 3.12.10), Streamlit multipage UI, SQLite, pandas, rapidfuzz.
- Package layout: `src/qa_engine` is an installable package (`pyproject.toml`, setuptools). It must be installed editable (`pip install -e .`) or `pages/*.py` imports fail with `ModuleNotFoundError: qa_engine`.
- Entry point: `app.py` (Streamlit). Pages: `pages/1_取込.py` .. `pages/5_分析結果.py`. Filenames contain Japanese; keep UTF-8.
- DB: `data/db/quality.sqlite3`, relative path -> Streamlit must be started from the repo root. Created automatically on first start from `src/qa_engine/storage/schema.sql` (`CREATE TABLE IF NOT EXISTS`, no migrations). After changing `schema.sql` in dev, delete `data/db/quality.sqlite3` and restart.
- All DB access goes through `src/qa_engine/storage/repository.py`. Pages must not contain raw SQL.
- Cross-page state: current session id lives in `st.session_state` (`src/qa_engine/app_state.py`). It is lost on browser reload / direct URL navigation; navigate via sidebar.
- AI integration is NOT implemented yet. Current logic is placeholder ("仮実装"):
  - header detection: `ingestion/naive_parser.py` (first line = header, CSV/TSV). Target: `ingestion/header_detector.py` via `AIProvider.extract_header`.
  - column suggestion: all columns marked suggested. Target: `AIProvider.suggest_columns`.
  - word mining: `analysis/qualitative.py::naive_mine_words` (regex char-class split, no morphological analysis). Target: `AIProvider.mine_words`.
  - scoring: `analysis/scoring.py::naive_calculate_scores` (provisional formula).
  - duplicate check: `checks/duplicate_check.py` (rapidfuzz, real implementation, O(n^2)).
- AI providers (`src/qa_engine/ai/`): `AIProvider` interface in `base.py`. `manual_relay_provider.py` = dev-time provider where the prompt is shown in the UI, the human pastes it into the IDE chat (i.e. you, Copilot), and pastes the answer back. Streamlit reruns the script on every interaction, so prompt display and response parsing must be split into two steps using `st.session_state`. `azure_provider.py` (future, production), `local_llm_provider.py` (future, local Qwen etc.) are stubs.
- Analysis results (structured data in DB) are intentionally separated from presentation (`report/formatter.py`). Output format will change often; do not couple it to analysis logic.

## 2. Obtain the source

The repository is transferred from another PC. Either:
- `git clone <repo URL provided by the user>` then `cd` into it, or
- the user has copied the folder. If copied, delete these if present because they are machine-specific: `.venv/`, `src/qa_engine.egg-info/`, `data/db/quality.sqlite3`, any `__pycache__/`.

If the repo URL is needed and not given, ask the user. Do not guess URLs.

## 3. Check prerequisites

```powershell
python --version
py -0p
git --version
```

Pick an interpreter with version >= 3.11 (prefer 3.12). Resolution order:
1. `python --version` reports >= 3.11 and is not the Microsoft Store alias stub -> use `python`.
2. Otherwise, if `py -0p` lists 3.12 or 3.11 -> use `py -3.12` (or `py -3.11`).
3. Otherwise STOP: tell the user Python 3.11+ is required and must be installed through the company-approved method.

Below, `<PY>` means the chosen launcher (`python` or `py -3.12`).

## 4. Create venv and install

```powershell
<PY> -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

- Do not run `pip install --upgrade pip` unless install fails because pip is too old.
- If install fails with SSL/proxy/connection errors -> follow rule in section 0 (stop and report). Typical fix is user-side: environment variables `HTTPS_PROXY`/`HTTP_PROXY`, or `pip config` with an internal index URL provided by their IT. Only apply such settings if the user supplies the values, and apply them scoped to the venv (`.\.venv\Scripts\python.exe -m pip config --site set global.index-url <url>`), not globally.

Verify:

```powershell
.\.venv\Scripts\python.exe -c "import streamlit, pandas, rapidfuzz, qa_engine; print('imports ok', streamlit.__version__)"
```

## 5. Smoke test (no UI)

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

Expected: first line `SMOKE TEST OK`, exit code 0, followed by three rows:
- 重複行の割合 = 0.5
- 重み付き語スコア平均 = 0.594
- 総合品質スコア(仮) = 39.8

The script uses a temp DB (does not touch `data/db/`), compiles `app.py` and all `pages/*.py`, and runs the whole pipeline on `data/samples/sample_defects.csv`. If it fails, fix the environment first; do not edit assertions to make it pass.

## 6. VS Code configuration

Select the interpreter: Command Palette -> `Python: Select Interpreter` -> `.\.venv\Scripts\python.exe`.
If the Python extension is not installed, tell the user (extension installation may be restricted by company policy); the app still runs from the terminal.

Create `.vscode/launch.json` (optional, enables F5 debug run):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Streamlit: app.py",
      "type": "debugpy",
      "request": "launch",
      "module": "streamlit",
      "args": [
        "run", "app.py",
        "--server.headless=true",
        "--server.address=localhost",
        "--server.port=8501",
        "--browser.gatherUsageStats=false"
      ],
      "cwd": "${workspaceFolder}",
      "python": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
      "env": { "PYTHONIOENCODING": "utf-8" },
      "justMyCode": true
    }
  ]
}
```

`.vscode/` is not in `.gitignore`; ask the user before committing it.

## 7. Run the app

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m streamlit run app.py --server.headless=true --server.address=localhost --server.port=8501 --browser.gatherUsageStats=false
```

- `--server.headless=true` also suppresses Streamlit's first-run email prompt (which would block a non-interactive terminal).
- Health check (from another terminal): `Invoke-WebRequest http://127.0.0.1:8501/_stcore/health -UseBasicParsing` -> content `ok`.
- If port 8501 is taken, use another port; do not kill unknown processes.
- If Windows Firewall shows a dialog, the user can deny network access; localhost binding does not need it.
- Open http://localhost:8501 in a browser (user action if you cannot open a browser).

## 8. Manual UI walkthrough (tell the user to do this, or do it if you have browser control)

Use the sidebar to move between pages (not the URL bar).
1. 取込: upload `data/samples/sample_defects.csv` -> click 取込実行 -> expect `セッション N を作成しました(5列 / 8行)`.
2. 列選択: uncheck ID, 発生日, 重要度 -> 確定 -> expect `確定しました: 工程, 不具合内容`.
3. 行チェック: threshold 90 -> 重複チェック実行 -> expect `4 / 8`.
4. ワードマイニングと重み付け: ワードマイニング実行 -> set 組立 to 1.0 -> 重みを保存 -> expect `保存しました`.
5. 分析結果: 分析実行 -> table with 3 rows (0.5 / 0.594 / 39.8 when weights match step 4) -> JSON download button available.

## 9. Known issues / troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `ModuleNotFoundError: qa_engine` | editable install missing or wrong interpreter | re-run `pip install -e .` with `.venv` python; check VS Code interpreter |
| `sqlite3.OperationalError: table ... has no column named ...` | old DB from previous schema | stop app, delete `data/db/quality.sqlite3`, restart |
| Pages 2-5 show 「先に「1. 取込」で…」 | session state lost (reload / URL navigation) | re-run 取込, navigate via sidebar |
| Mojibake in terminal output | console encoding | set `$env:PYTHONIOENCODING='utf-8'` |
| Cannot delete `quality.sqlite3` ("busy") | Streamlit still holds the file | stop Streamlit first |
| `Activate.ps1 cannot be loaded` | execution policy | don't activate; call `.venv\Scripts\python.exe` directly |
| pip SSL / proxy errors | corporate network | stop and report (section 0) |

## 10. Completion report

When done, report to the user (in Japanese):
- Python version and launcher used
- result of section 4 verify command
- full output of the smoke test
- whether the app started and the health check returned `ok`
- anything skipped or blocked, with the exact error text
