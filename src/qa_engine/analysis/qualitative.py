"""定性分析: AIを使わない簡易ワードマイニングと、ユーザーの重み付けの集約。"""

import re
from collections import Counter

from qa_engine.ai.base import WordMiningResult

_TOKEN_PATTERN = re.compile(r"[一-龥々ぁ-んァ-ヶーa-zA-Z0-9]{2,}")


def naive_mine_words(texts: list[str], top_n: int = 30) -> list[WordMiningResult]:
    """文字種の連続で区切る簡易トークナイズと頻度集計。日本語の語の区切りは粗い。"""
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(_TOKEN_PATTERN.findall(text))
    most_common = counter.most_common(top_n)
    if not most_common:
        return []
    max_freq = most_common[0][1]
    return [
        WordMiningResult(term=term, frequency=freq, ai_score=round(freq / max_freq, 3))
        for term, freq in most_common
    ]


def weighted_average(frequencies: list[int], weights: list[float]) -> float:
    """頻度で重み付けしたユーザー重みの平均(0〜1)。"""
    total = sum(frequencies)
    if total == 0:
        return 0.0
    return sum(f * w for f, w in zip(frequencies, weights)) / total
