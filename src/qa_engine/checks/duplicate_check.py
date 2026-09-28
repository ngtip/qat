"""重複検出チェック。

Levenshtein系の距離(rapidfuzz)は高速なスクリーニング用途として使う。
表記ゆれはあるが意味的に同一な重複までは拾えないため、将来的に埋め込みベースの
類似度チェックなど、他の手法と組み合わせることを想定している。
"""

import pandas as pd
from rapidfuzz import fuzz, process

from qa_engine.checks.base import Check, CheckResult


class DuplicateCheck(Check):
    name = "duplicate_check"

    def __init__(self, similarity_threshold: float = 90.0):
        self.similarity_threshold = similarity_threshold

    def run(self, df: pd.DataFrame, target_columns: list[str]) -> list[CheckResult]:
        texts = df[target_columns].fillna("").astype(str).agg(" ".join, axis=1).tolist()
        scores = process.cdist(texts, texts, scorer=fuzz.ratio)

        results = []
        for i in range(len(texts)):
            matches = [
                {"row_index": j, "similarity": round(float(scores[i][j]), 1)}
                for j in range(len(texts))
                if j != i and scores[i][j] >= self.similarity_threshold
            ]
            results.append(CheckResult(row_index=i, detail={"duplicate_matches": matches}))
        return results
