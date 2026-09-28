"""利用可能なチェックを登録・列挙するレジストリ。

新しいチェックを追加する際は、ここに登録するだけでUI側(3_行チェック.py)から選択できるようにする。
"""

from qa_engine.checks.base import Check
from qa_engine.checks.duplicate_check import DuplicateCheck

_REGISTRY: dict[str, Check] = {
    DuplicateCheck.name: DuplicateCheck(),
}


def available_checks() -> dict[str, Check]:
    return dict(_REGISTRY)


def get_check(name: str) -> Check:
    return _REGISTRY[name]
