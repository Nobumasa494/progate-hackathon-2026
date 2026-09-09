"""最新goalをSupabaseから取得し、target_daily_reduction_kcal付きJSONで表示する（たたき台）。

使い方
    python example_get_goal.py <user_id>
"""

from __future__ import annotations

import json
import sys

from goal_repository import get_latest_goal_with_daily_reduction


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python example_get_goal.py <user_id>", file=sys.stderr)
        raise SystemExit(2)
    user_id = sys.argv[1]
    result = get_latest_goal_with_daily_reduction(user_id)
    if result is None:
        print(f"goals に user_id={user_id} のレコードがありません", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()