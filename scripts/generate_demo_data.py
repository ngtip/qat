"""デモ用のダミー障害票(架空データ)を生成する。固定シードなので何度実行しても同じ内容になる。

出力: data/samples/bug_tickets_demo.csv (UTF-8 BOM付き。先頭2行は表題と注記で、3行目がヘッダ)
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "samples" / "bug_tickets_demo.csv"
ROW_COUNT = 80
SEED = 20260930

HEADER = [
    "障害ID", "起票日", "発見工程", "機能", "重要度", "現象",
    "原因区分", "原因詳細", "対策", "担当者", "ステータス", "対応工数h",
]

# (機能, 現象の言い回し候補, 基本の重要度, 原因区分, 原因詳細, 対策)
# 言い回し候補が複数あるものは、表記ゆれのある重複報告として使う。
PHENOMENA = [
    ("ログイン", ["パスワード誤入力時にエラーメッセージが表示されない"], "B",
     "実装誤り", "入力チェック後のメッセージ設定処理が呼ばれていなかった", "メッセージ設定処理を追加し、テストケースを追加"),
    ("ログイン", ["セッションタイムアウト後に操作するとシステムエラー画面が表示される",
                 "タイムアウト後の操作でシステムエラーになる"], "A",
     "設計誤り", "タイムアウト時の画面遷移が設計で考慮されていなかった", "ログイン画面へ遷移する共通処理を追加"),
    ("ログイン", ["全角文字を含むIDでログインできない"], "C",
     "仕様漏れ", "仕様書にIDの文字種の記載がなかった", "仕様書を更新し、入力チェックを追加"),
    ("会員登録", ["郵便番号から住所が自動入力されない"], "C",
     "環境・設定", "住所検索APIの接続先設定が検証環境のままだった", "接続先設定を修正"),
    ("会員登録", ["登録完了メールが送信されない", "会員登録後に完了メールが届かない"], "A",
     "環境・設定", "メールサーバの認証設定が漏れていた", "認証設定を追加し、送信ログの監視を追加"),
    ("会員登録", ["必須項目が未入力でも登録できてしまう"], "B",
     "実装誤り", "サーバ側の必須チェックが実装されていなかった", "サーバ側に必須チェックを追加"),
    ("商品検索", ["検索結果の件数表示が実際の件数と一致しない"], "C",
     "実装誤り", "件数取得のSQLに絞り込み条件が反映されていなかった", "件数取得SQLを修正"),
    ("商品検索", ["半角カナで検索すると結果が0件になる", "半角カナ検索でヒットしない"], "B",
     "仕様漏れ", "仕様書に検索語の正規化ルールの記載がなかった", "検索語の全角変換を追加し、仕様書を更新"),
    ("商品検索", ["価格順の並び替えが正しく動作しない"], "C",
     "実装誤り", "価格を文字列として比較していた", "数値として比較するよう修正"),
    ("商品検索", ["検索結果の2ページ目以降が表示されない"], "B",
     "実装誤り", "ページ番号の計算で境界値の扱いが誤っていた", "ページング処理を修正し、境界値テストを追加"),
    ("カート", ["数量を変更しても合計金額が更新されない", "数量変更後に合計金額が再計算されない"], "A",
     "実装誤り", "数量変更イベントで再計算処理が呼ばれていなかった", "再計算処理の呼び出しを追加"),
    ("カート", ["カート内の商品が削除できない"], "B",
     "実装誤り", "削除時に参照するキーが誤っていた", "削除キーを修正"),
    ("カート", ["在庫切れ商品がカートに追加できてしまう"], "A",
     "設計誤り", "在庫チェックのタイミングが設計で考慮されていなかった", "カート追加時に在庫チェックを追加"),
    ("決済", ["クレジットカード決済で二重に課金される", "クレカ決済時に二重課金が発生する"], "S",
     "設計誤り", "決済APIの再送制御が設計で考慮されていなかった", "冪等キーによる二重送信防止を追加"),
    ("決済", ["決済完了画面で注文番号が表示されない"], "B",
     "実装誤り", "注文番号の受け渡し項目名が誤っていた", "項目名を修正"),
    ("決済", ["ポイント利用時に端数の計算が誤っている"], "A",
     "仕様漏れ", "仕様書に端数処理(切り捨て/四捨五入)の記載がなかった", "端数処理を切り捨てに統一し、仕様書を更新"),
    ("決済", ["決済タイムアウト時に注文データがロールバックされない"], "S",
     "設計誤り", "トランザクション範囲の設計誤り", "トランザクション範囲を見直し、異常系テストを追加"),
    ("帳票出力", ["月次売上帳票の合計行がずれる"], "B",
     "実装誤り", "合計行の出力位置の計算誤り", "出力位置の計算を修正"),
    ("帳票出力", ["CSV出力で文字化けが発生する", "CSV出力時に文字化けする"], "B",
     "実装誤り", "文字コードの指定が漏れていた", "文字コードをUTF-8(BOM付き)に統一"),
    ("帳票出力", ["PDF帳票の改ページ位置が不正"], "C",
     "実装誤り", "明細行数の上限値が誤っていた", "上限値を修正"),
    ("管理画面", ["権限のないユーザーが管理メニューを表示できる"], "S",
     "設計誤り", "画面単位の権限チェックが設計で漏れていた", "全画面に権限チェックを追加し、レビュー観点に追加"),
    ("管理画面", ["一覧画面の絞り込み条件が画面遷移後にリセットされる"], "C",
     "仕様漏れ", "仕様書に検索条件の保持の記載がなかった", "検索条件をセッションに保持"),
    ("管理画面", ["データ更新時に更新日時が更新されない"], "B",
     "実装誤り", "更新日時の設定処理が漏れていた", "共通の更新処理に日時設定を追加"),
    ("バッチ連携", ["夜間バッチが異常終了する", "夜間バッチが途中で異常終了した"], "A",
     "データ不備", "移行データに不正な日付が含まれていた", "データを補正し、入力チェックを追加"),
    ("バッチ連携", ["連携ファイルの件数チェックでエラーになる"], "B",
     "テスト漏れ", "ヘッダ行を含む件数のパターンをテストしていなかった", "件数計算を修正し、テストケースを追加"),
    ("バッチ連携", ["月末日の日付変換で翌月扱いになる"], "A",
     "実装誤り", "日付計算で月末の扱いが誤っていた", "日付ライブラリの関数に置き換え"),
]

# 現象の前に付ける発生条件。同じ現象でも条件が違えば別の障害として扱う。
CONTEXTS = [
    "初回ログイン直後の操作で", "iPhoneのSafariで閲覧した場合に", "管理者権限のアカウントで操作すると",
    "大量データ(1万件以上)を扱う場合に", "月末日の夜間処理と重なった時に", "同じ画面を2つのタブで開いていると",
    "会員情報を変更した直後に", "ポイントとクーポンを併用した場合に", "検索条件を3つ以上指定した場合に",
    "セール期間中のアクセス集中時に", "古いブラウザ(IE互換モード)で", "CSVファイル取込後の初回操作で",
    "メンテナンス明けの最初の処理で", "外部システムの応答が遅い時に", "多言語(英語)表示に切り替えた状態で",
    "ゲスト購入の手順で", "境界値のテストデータを使うと", "前回の操作から30分以上経過してから",
]
DUPLICATE_GAP_DAYS = 5

PHASES = ["単体テスト", "結合テスト", "システムテスト", "受入テスト", "本番"]
ASSIGNEES = [f"担当{c}" for c in "ABCDEFGH"]
SEVERITY_ORDER = ["S", "A", "B", "C"]
HOURS_RANGE = {"S": (8, 24), "A": (4, 16), "B": (2, 8), "C": (0.5, 3)}


def _phase_for(day_offset: int, rng: random.Random) -> str:
    """期間の前半ほど上流工程、後半ほど下流工程になるように選ぶ。"""
    center = day_offset / 60 * (len(PHASES) - 1)
    index = round(center + rng.uniform(-1.0, 1.0))
    index = min(max(index, 0), len(PHASES) - 1)
    if PHASES[index] == "本番" and rng.random() < 0.6:
        index -= 1
    return PHASES[index]


def _severity(base: str, rng: random.Random) -> str:
    index = SEVERITY_ORDER.index(base)
    roll = rng.random()
    if roll < 0.15:
        index = max(index - 1, 0)
    elif roll < 0.30:
        index = min(index + 1, len(SEVERITY_ORDER) - 1)
    return SEVERITY_ORDER[index]


def _status(day_offset: int, rng: random.Random) -> str:
    if day_offset < 40:
        return "完了" if rng.random() < 0.9 else "対応中"
    roll = rng.random()
    if roll < 0.5:
        return "完了"
    if roll < 0.8:
        return "対応中"
    return "未着手"


def generate_rows(rng: random.Random) -> list[list[str]]:
    """表記ゆれのある現象は、同じ発生条件・別の言い回しで2件起票された重複報告として入れる。
    それ以外は(現象, 発生条件)の組み合わせが重ならないように選ぶ。"""
    start = date(2026, 8, 1)
    used: set[tuple[str, str]] = set()
    entries = []

    for spec in (p for p in PHENOMENA if len(p[1]) > 1):
        context = rng.choice(CONTEXTS)
        used.add((spec[1][0], context))
        offset = rng.randint(0, 60 - DUPLICATE_GAP_DAYS)
        for text, day in ((spec[1][0], offset), (spec[1][1], offset + rng.randint(0, DUPLICATE_GAP_DAYS))):
            entries.append((day, spec, f"{context}、{text}"))

    while len(entries) < ROW_COUNT:
        spec, context = rng.choice(PHENOMENA), rng.choice(CONTEXTS)
        if (spec[1][0], context) in used:
            continue
        used.add((spec[1][0], context))
        entries.append((rng.randint(0, 60), spec, f"{context}、{spec[1][0]}"))

    entries = [
        (offset, function, text, base_severity, cause, detail, measure)
        for offset, (function, _, base_severity, cause, detail, measure), text in entries
    ]
    entries.sort(key=lambda e: e[0])
    rows = []
    for number, (offset, function, text, base_severity, cause, detail, measure) in enumerate(entries, 1):
        severity = _severity(base_severity, rng)
        status = _status(offset, rng)
        low, high = HOURS_RANGE[severity]
        hours = round(rng.uniform(low, high) * 2) / 2
        row = [
            f"BUG-{number:04d}",
            (start + timedelta(days=offset)).strftime("%Y/%m/%d"),
            _phase_for(offset, rng),
            function,
            severity,
            text,
            cause,
            detail,
            measure if status != "未着手" else "",
            rng.choice(ASSIGNEES),
            status,
            "" if status == "未着手" else f"{hours:g}",
        ]
        if rng.random() < 0.04:
            row[7] = ""
        if rng.random() < 0.03:
            row[9] = ""
        rows.append(row)
    return rows


def main() -> None:
    rng = random.Random(SEED)
    rows = generate_rows(rng)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("障害管理台帳(ダミーデータ) 対象期間: 2026/08/01〜2026/09/30\r\n")
        f.write("※本データは架空のものです。実在のシステム・案件とは関係ありません。\r\n")
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"{OUTPUT} に {len(rows)} 件書き出しました")


if __name__ == "__main__":
    main()
