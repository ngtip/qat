"""フリーフォーマットの入力からヘッダ情報を検出する。

AIProvider.extract_header に委譲する薄いラッパー。ヘッダが検出できない入力を
拒否するバリデーションはここで行う。
"""

from qa_engine.ai.base import AIProvider, HeaderInfo


class HeaderNotFoundError(Exception):
    pass


def detect_header(provider: AIProvider, raw_text: str) -> HeaderInfo:
    header = provider.extract_header(raw_text)
    if not header.columns:
        raise HeaderNotFoundError("ヘッダ情報を検出できませんでした")
    return header
