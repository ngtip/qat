"""ヘッダ情報(AI検出・簡易検出のどちらでも)に従って、入力全体を行データに分解する。"""

import csv
import io

from qa_engine.ai.base import HeaderInfo
from qa_engine.ingestion.header_detector import HeaderNotFoundError


def parse_with_header(raw_text: str, header_info: HeaderInfo) -> tuple[list[str], list[dict]]:
    lines = raw_text.splitlines()
    if not 0 <= header_info.header_row_index < len(lines):
        raise HeaderNotFoundError("ヘッダ行の位置が入力の範囲外です")

    body = "\n".join(lines[header_info.header_row_index:])
    records = [r for r in csv.reader(io.StringIO(body), delimiter=header_info.delimiter)
               if any(cell.strip() for cell in r)]
    header = [c.strip() for c in records[0]]

    if len(header) < 2 or any(not h for h in header):
        raise HeaderNotFoundError("ヘッダ行に2列以上の空でない見出しが必要です")
    if len(set(header)) != len(header):
        raise HeaderNotFoundError("ヘッダに重複した列名があります")

    rows = [
        {h: (record[i].strip() if i < len(record) else "") for i, h in enumerate(header)}
        for record in records[1:]
    ]
    return header, rows
