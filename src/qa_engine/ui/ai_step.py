"""AI処理の1工程を画面上で実行する部品。サイドバーで選んだ呼び先に応じて処理を切り替える。

手動中継では、Streamlit が操作のたびにスクリプトを再実行するため、
「プロンプトの提示」と「応答の取込」を別の操作に分け、取込んだ結果を st.session_state に保持する。
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import streamlit as st

from qa_engine.ai.base import ProviderNotConfiguredError
from qa_engine.ai.providers import PROVIDER_LABELS, get_provider
from qa_engine.ai.tasks import AIResponseError, AITask
from qa_engine.config import load_settings
from qa_engine.ingestion.header_detector import HeaderNotFoundError
from qa_engine.storage import repository
from qa_engine.storage.connection import get_streamlit_connection
from qa_engine.ui.sidebar import current_provider

_PARSE_ERRORS = (AIResponseError, HeaderNotFoundError)


@dataclass
class StepOutcome:
    value: Any
    interaction_id: int | None


def run_ai_step(
    step_key: str,
    task: AITask,
    inputs: dict[str, Any],
    naive_fn: Callable[[], Any],
    session_id: int | None = None,
) -> StepOutcome | None:
    """結果が揃っていれば StepOutcome を、まだ(応答待ち・エラー)なら None を返す。"""
    provider = current_provider()
    st.caption(f"AIの呼び先: {PROVIDER_LABELS[provider]}")

    if provider == "naive":
        try:
            return StepOutcome(naive_fn(), None)
        except HeaderNotFoundError as e:
            st.error(f"取込できません: {e}")
            return None

    prompt = task.build_prompt(**inputs)
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
    state_key = f"ai_step::{step_key}::{provider}::{digest}"

    if state_key in st.session_state:
        st.success(f"{task.label}: AIの応答を取込済みです。")
        if st.button("応答を取込み直す", key=f"reset::{state_key}"):
            del st.session_state[state_key]
            st.rerun()
        return st.session_state[state_key]

    if provider == "manual_relay":
        response = _relay_form(task, prompt, state_key)
    else:
        response = _call_automatic(provider, prompt)
    if response is None:
        return None

    try:
        value = task.parse_response(response, **inputs)
    except _PARSE_ERRORS as e:
        st.error(f"応答を読み取れませんでした: {e}")
        return None

    conn = get_streamlit_connection()
    interaction_id = repository.log_ai_interaction(conn, session_id, task.key, provider, prompt, response)
    st.session_state[state_key] = StepOutcome(value, interaction_id)
    st.rerun()


def _relay_form(task: AITask, prompt: str, state_key: str) -> str | None:
    st.info(
        f"**{task.label}をIDEのAIチャットで実行します**\n\n"
        "1. 下のプロンプトを、右上のボタンでコピーする\n"
        "2. IDEのAIチャット(GitHub Copilot など)に貼り付けて送信する\n"
        "3. 返ってきた応答をそのまま下の欄に貼り付けて「応答を取込」を押す"
    )
    st.code(prompt, language="text", wrap_lines=True, height=300)
    with st.form(f"relay::{state_key}"):
        response = st.text_area("AIの応答", height=220, placeholder="AIチャットの応答をここに貼り付け")
        submitted = st.form_submit_button("応答を取込", type="primary")
    if not submitted:
        return None
    if not response.strip():
        st.error("応答が空です。")
        return None
    return response


def _call_automatic(provider: str, prompt: str) -> str | None:
    client = get_provider(provider, load_settings())
    try:
        return client.complete(prompt)
    except ProviderNotConfiguredError as e:
        st.warning(f"{e} サイドバーで「手動中継」か「簡易ロジック」を選んでください。")
        return None
