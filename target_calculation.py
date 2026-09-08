"""体重目標から1日当たりの目標削減カロリーを算出する（たたき台）。

仕様
- daily_reduction_kcal = (current_weight_kg - target_weight_kg) * 7200 / 残り日数
- 保存はせず、goalsテーブルの値から毎日計算する
- 計算結果は target_daily_reduction_kcal として他の機能へ渡す
  （例: 食事・運動推奨のリクエストに同キーを添付）

使い方（たたき台CLI）
    python target_calculation.py latest_goal.json
    標準入力から読み込む場合: cat latest_goal.json | python target_calculation.py -
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import Optional

KCAL_PER_KG = 7200  # 体重1kgの増減 ≒ 7200kcal


def parse_date(value: str) -> date:
    """"2026-10-07" 等（あればタイムゾーン付き）を date に変換する。"""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def remaining_days(target_date: date, today: Optional[date] = None) -> int:
    """今日から期日まで（当日を含めると1日）の残り日数。"""
    today = today or date.today()
    remaining = (target_date - today).days
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
    """1日当たりの目標削減カロリーを返す（マイナスの場合は増量目標）。"""
    days = remaining_days(target_date, today)
    kcal = (current_weight_kg - target_weight_kg) * KCAL_PER_KG / days
    return round(kcal, 1)


def enrich_goal(goal: dict, today: Optional[date] = None) -> dict:
    """goalsテーブルの1件JSONに target_daily_reduction_kcal を付与して返す。"""
    result = dict(goal)
    result["target_daily_reduction_kcal"] = calc_target_daily_reduction_kcal(
        current_weight_kg=float(result["current_weight_kg"]),
        target_weight_kg=float(result["target_weight_kg"]),
        target_date=parse_date(result["target_date"]),
        today=today,
    )
    return result


def load_json(source: str) -> dict:
    if source == "-":
        return json.load(sys.stdin)
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python target_calculation.py <goal.json | ->", file=sys.stderr)
        raise SystemExit(2)
    goal = load_json(sys.argv[1])
    result = enrich_goal(goal)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()