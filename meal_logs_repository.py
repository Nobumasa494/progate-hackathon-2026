"""meal_logsテーブル（Supabase/Postgres）へ接続し、食事ログのCRUDを行う。

【Supabase上の meal_logs テーブル構成】
    user_id                   : uuid (PK, auth.users(id)への外部キー)
    dish_name                 : text (検索した料理名。機能1への入力と同じ)
    suggested_replacement_name : text (AIが提案したレシピ。機能1の出力)
    original_calories         : int4 (元の料理の推定カロリー。機能1の出力)
    replacement_calories      : int4 (置き換え料理の推定カロリー。機能1の出力)
    did_replace               : bool (実際に置き換えたかどうか)
    actual_calories           : int4 (実際に摂取したカロリー)
    calorie_diff              : int4 (original_calories - actual_calories。このログでの削減量)
    created_at                : timestamp (自動記録)

【使い方】
    from meal_logs_repository import fetch_logs, insert_log, fetch_weekly_summary
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from supabase import Client, create_client


def _load_env() -> None:
    """ .env ファイルから環境変数（SUPABASE_URL, SUPABASE_KEY）を読み込む。 """
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    """Supabaseクライアントを作成する。未指定時は環境変数から読む。"""
    url = url or os.environ["SUPABASE_URL"]
    key = key or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def insert_log(
    user_id: str,
    dish_name: str,
    suggested_replacement_name: str,
    original_calories: int,
    replacement_calories: int,
    did_replace: bool,
    actual_calories: int,
    client: Optional[Client] = None,
) -> dict:
    """食事ログを1件追加する。calorie_diff は original - actual で自動計算する。

    仕様:
        - did_replace=True（置き換えた）  → actual_calories は replacement 側の値を指定
        - did_replace=False（我慢した）    → actual_calories は original 側の値（=削減なし、差分0）を指定
    """
    client = client or get_client()
    calorie_diff = original_calories - actual_calories
    resp = (
        client.table("meal_logs")
        .insert(
            {
                "user_id": user_id,
                "dish_name": dish_name,
                "suggested_replacement_name": suggested_replacement_name,
                "original_calories": original_calories,
                "replacement_calories": replacement_calories,
                "did_replace": did_replace,
                "actual_calories": actual_calories,
                "calorie_diff": calorie_diff,
            }
        )
        .execute()
    )
    return resp.data[0]


def fetch_logs(
    user_id: str,
    client: Optional[Client] = None,
    limit: int = 50,
    order_desc: bool = True,
) -> list:
    """user_id の食事ログを新しい順に取得する。"""
    client = client or get_client()
    query = (
        client.table("meal_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=order_desc)
        .limit(limit)
    )
    resp = query.execute()
    return resp.data


def fetch_weekly_summary(
    user_id: str,
    client: Optional[Client] = None,
) -> list:
    """宴位単位（週単位）のカロリー削減積算を返す。

    元のSQL（Supabaseで実装済みのものと同等）:
        select date_trunc('week', logged_at) as week,
               sum(calorie_diff) as total_saved_kcal
        from meal_logs
        where user_id = auth.uid()
        group by 1
        order by 1 desc;

    注意:
        Supabase Pythonクライアントは group by が直接使えないため、
        全件取得してPython側で週ごとに合計する方式にしている。
        大規模にならなければ十分動作する。
    """
    client = client or get_client()
    logs = fetch_logs(user_id, client, limit=10000, order_desc=False)

    # 週初め（月曜日）をキーに集計する
    weeks: dict[str, int] = {}
    for log in logs:
        week_start = _week_start(log["created_at"])
        weeks[week_start] = weeks.get(week_start, 0) + int(log["calorie_diff"] or 0)

    # 新しい週順に並べて返す
    summary = [
        {"week": week, "total_saved_kcal": total}
        for week, total in sorted(weeks.items(), reverse=True)
    ]
    return summary


def _week_start(created_at: str) -> str:
    """created_at（ISO8601）からその週の月曜日の日付（YYYY-MM-DD）を返す。"""
    from datetime import datetime, timedelta

    # "2026-09-10T12:34:56Z" 等から日付を抜き出す
    if created_at and "T" in created_at:
        dt = datetime.fromisoformat(created_at.split("T")[0])
    else:
        dt = datetime.fromisoformat(created_at[:10])
    # Pythonでは月曜日=0。今週の月曜を求める
    monday = dt - timedelta(days=dt.weekday())
    return monday.date().isoformat()