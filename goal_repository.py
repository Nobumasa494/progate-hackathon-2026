"""goalsテーブル（Supabase/Postgres）へ接続し、最新goalを取得して計算する（たたき台）。

goals.sql で定義したテーブルから最新1件を読み、target_calculation を適用した結果を
target_daily_reduction_kcal 付きで返す。daily_reduction_kcal は保存せず毎日計算する。

環境変数（.env は python-dotenv で読み込み可）
    SUPABASE_URL  例: https://xxxx.supabase.co
    SUPABASE_KEY  anon key または service_role key

使い方
    from goal_repository import get_latest_goal_with_daily_reduction
    result = get_latest_goal_with_daily_reduction(user_id="....")
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

from target_calculation import enrich_goal


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    """Supabaseクライアントを作成する。url/key未指定時は環境変数から読む。"""
    url = url or os.environ["SUPABASE_URL"]
    key = key or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def fetch_latest_goal(
    user_id: str, client: Optional[Client] = None
) -> Optional[dict]:
    """user_id の最新（created_at降順先頭）のgoal1件を返す。無ければNone。"""
    client = client or get_client()
    resp = (
        client.table("goals")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data
    return rows[0] if rows else None


def get_latest_goal_with_daily_reduction(
    user_id: str, client: Optional[Client] = None
) -> Optional[dict]:
    """最新goalを取得し、target_daily_reduction_kcal を付与して返す。"""
    goal = fetch_latest_goal(user_id, client)
    if goal is None:
        return None
    return enrich_goal(goal)