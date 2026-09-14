"""体重目標から1日当たりの目標削減カロリーを算出する。

【計算式】
    daily_reduction_kcal = (current_weight_kg - target_weight_kg) * 7200 / 残り日数

    - 7200kcal = 脂肪1kgあたりの熱量（体重1kgの増減 ≒ 7200kcal）
    - 例: (75kg - 65kg) * 7200 / 30日 = 2400 kcal/日

【仕様】
    - 計算結果は保存しない（goalsテーブルの値から毎日計算する）
    - 体重が変われば自動的に目標もずれるため

【使い方】
    # Pythonコードから
    from target_calculation import enrich_goal
    result = enrich_goal(goal_dict)

    # コマンドラインから
    python target_calculation.py <goal.json>
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import Optional

# 体重1kgの増減に相当するカロリー（脂肪の熱量）
KCAL_PER_KG = 7200

# 1日あたりの削減カロリーとして安全とされる目安の上限
MAX_SAFE_DAILY_REDUCTION_KCAL = 1000


def parse_date(value: str) -> date:
    """日付文字列を date オブジェクトに変換する。

    対応フォーマット:
        "2026-10-07"           → date(2026, 10, 7)
        "2026-10-07T00:00:00Z" → date(2026, 10, 7)  （タイムゾーン付きもOK）
    """
    try:
        # "2026-10-07" 形式をパース
        return date.fromisoformat(value)
    except ValueError:
        # タイムゾーン付き（"2026-10-07T00:00:00Z"）の場合は別処理
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def remaining_days(target_date: date, today: Optional[date] = None) -> int:
    """今日から期日までの残り日数を返す。

    例: today=2026-09-10, target_date=2026-10-10 → 30日

    注意: 期日が過去の場合はエラーを返す（残り日数が0以下は計算できない）
    """
    today = today or date.today()  # today未指定なら今日の日付を使う
    remaining = (target_date - today).days  # 日付の差分を計算

    if remaining < 1:
        raise ValueError(
            f"target_date={target_date.isoformat()} は期限切れ（残り{remaining}日）です"
        )
    return remaining


def calc_target_daily_reduction_kcal(
    current_weight_kg: float,
    target_weight_kg: float,
    target_date: date,
    today: Optional[date] = None,
) -> float:
    """1日当たりの目標削減カロリーを計算する。

    計算式:
        (現在体重 - 目標体重) * 7200 / 残り日数

    例:
        (75.0 - 65.0) * 7200 / 30 = 2400.0 kcal/日

    戻り値が正の値 → 減量目標
    戻り値が負の値 → 増量目標
    """
    days = remaining_days(target_date, today)
    kcal = (current_weight_kg - target_weight_kg) * KCAL_PER_KG / days
    return round(kcal, 1)  # 小数点以下1桁で四捨五入


def enrich_goal(goal: dict, today: Optional[date] = None) -> dict:
    """goalsテーブルの1件JSONに target_daily_reduction_kcal を付与して返す。

    入力（goalsテーブルの1行）:
        {
            "user_id": "...",
            "current_weight_kg": 75.0,
            "target_weight_kg": 65.0,
            "target_date": "2026-10-10"
        }

    出力（target_daily_reduction_kcal が追加される）:
        {
            "user_id": "...",
            "current_weight_kg": 75.0,
            "target_weight_kg": 65.0,
            "target_date": "2026-10-10",
            "target_daily_reduction_kcal": 2400.0   ← これが追加される
        }
    """
    result = dict(goal)  # 元のデータを変更しないようコピーする

    current_weight_kg = float(result["current_weight_kg"])
    target_weight_kg = float(result["target_weight_kg"])

    # target_daily_reduction_kcal を計算して追加
    result["target_daily_reduction_kcal"] = calc_target_daily_reduction_kcal(
        current_weight_kg=current_weight_kg,
        target_weight_kg=target_weight_kg,
        target_date=parse_date(result["target_date"]),
        today=today,
    )

    # ゴールまでに合計で減らす必要があるカロリー（AIには使わない、正直に見せる用）
    result["total_remaining_kcal"] = round(
        (current_weight_kg - target_weight_kg) * KCAL_PER_KG, 1
    )

    # 安全とされる目安を超えるペースかどうか
    result["is_unsafe_pace"] = result["target_daily_reduction_kcal"] > MAX_SAFE_DAILY_REDUCTION_KCAL

    return result


def load_json(source: str) -> dict:
    """JSONファイルを読み込む。

    source="-" の場合は標準入力（パイプから受け取る場合）
    """
    if source == "-":
        return json.load(sys.stdin)
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    """コマンドラインから実行する場合のエントリーポイント。

    使い方:
        python target_calculation.py <goal.json>
        cat goal.json | python target_calculation.py -
    """
    if len(sys.argv) != 2:
        print("usage: python target_calculation.py <goal.json | ->", file=sys.stderr)
        raise SystemExit(2)

    # JSONファイルを読み込む
    goal = load_json(sys.argv[1])

    # target_daily_reduction_kcal を計算して付与
    result = enrich_goal(goal)

    # 結果をJSON形式で出力
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
