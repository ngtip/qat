"""Streamlitプロセス内で共有するDB接続。"""

import streamlit as st

from qa_engine.config import load_settings
from qa_engine.storage.db import get_connection, init_db


@st.cache_resource
def get_streamlit_connection():
    settings = load_settings()
    init_db(settings.db_path)
    return get_connection(settings.db_path, check_same_thread=False)
