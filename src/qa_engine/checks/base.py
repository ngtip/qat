"""行別チェック処理の共通インターフェース。

チェックを追加する場合はこのクラスを継承し、registry.py に登録する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class CheckResult:
    row_index: int
    detail: dict


class Check(ABC):
    name: str

    @abstractmethod
    def run(self, df: pd.DataFrame, target_columns: list[str]) -> list[CheckResult]:
        """対象列に対してチェックを実行し、行ごとの結果を返す。"""
