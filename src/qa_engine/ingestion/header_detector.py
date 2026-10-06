"""AIを使わない簡易ヘッダ検出。AI経由の検出結果と同じ HeaderInfo を返す。"""

import csv
import io

from qa_engine.ai.base import HeaderInfo

HEAD_LINE_LIMIT = 30


class HeaderNotFoundError(Exception):
    pass


def detect_header_naive(raw_text: str) -> HeaderInfo:
    """先頭30行のうち、区切られた列数が最大になる最初の行をヘッダとみなす。"""
    lines = raw_text.splitlines()[:HEAD_LINE_LIMIT]
    if not any(line.strip() for line in lines):
        raise HeaderNotFoundError("入力が空です")

    delimiter = "\t" if any("\t" in line for line in lines) else ","
    counts = []
    for line in lines:
        fields = next(csv.reader(io.StringIO(line), delimiter=delimiter), [])
        filled = [f for f in fields if f.strip()]
        counts.append(len(fields) if len(filled) == len(fields) else 0)

    best = max(counts)
    if best < 2:
        raise HeaderNotFoundError("ヘッダ情報を検出できませんでした(2列以上の見出し行が必要です)")
    index = counts.index(best)
    columns = [c.strip() for c in next(csv.reader(io.StringIO(lines[index]), delimiter=delimiter))]
    return HeaderInfo(header_row_index=index, delimiter=delimiter, columns=columns, notes="簡易検出")
