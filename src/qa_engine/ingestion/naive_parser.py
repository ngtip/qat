"""AI連携前の仮実装: 入力をCSV/TSVとして素朴に解析し、1行目をヘッダとして扱う。

将来は header_detector(AIProvider.extract_header)に置き換える。
"""

import csv
import io

from qa_engine.ingestion.header_detector import HeaderNotFoundError


def parse_free_text(raw_text: str) -> tuple[list[str], list[dict]]:
    lines = [line for line in raw_text.splitlines() if line.strip()]
    if not lines:
        raise HeaderNotFoundError("入力が空です")

    delimiter = "\t" if "\t" in lines[0] else ","
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))

    header = [cell.strip() for cell in rows[0]]
    if len(header) < 2 or any(not h for h in header):
        raise HeaderNotFoundError(
            "ヘッダ情報を検出できませんでした(1行目に2列以上の空でない見出しが必要です)"
        )
    if len(set(header)) != len(header):
        raise HeaderNotFoundError("ヘッダに重複した列名があります")

    data_rows = [
        {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)}
        for row in rows[1:]
    ]
    return header, data_rows
