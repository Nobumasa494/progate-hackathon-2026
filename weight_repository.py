"""weight_logsテーブル（Supabase/Postgres）へ接続し、体重記録のCRUDを行う。

【Supabase上の weight_logs テーブル構成】
    user_id    : uuid (PK, auth.users(id)への外部キー)
    weight_kg  : numeric (記録した体重)
    created_at : timestamp (自動記録)

【使い方】
    from weight_repository import insert_weight_log, get_weight_logs, get_latest_weight
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
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    url = url or os.environ["SUPABASE_URL"]
    key = key or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def insert_weight_log(user_id: str, weight_kg: float, client: Optional[Client] = None) -> None:
    client = client or get_client()
    client.table("weight_logs").insert({
        "user_id": user_id,
        "weight_kg": weight_kg,
    }).execute()


def get_weight_logs(user_id: str, client: Optional[Client] = None) -> list[dict]:
    """そのユーザーの体重記録を、記録した順（古い順）に返す。"""
    client = client or get_client()
    response = (
        client.table("weight_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("id")
        .execute()
    )
    return response.data


def get_latest_weight(user_id: str, client: Optional[Client] = None) -> Optional[float]:
    """そのユーザーの最新の体重（kg）を返す。記録が無ければNone。

    goal_repository が「現在の体重」として使う値はここから取得する。
    """
    client = client or get_client()
    response = (
        client.table("weight_logs")
        .select("weight_kg")
        .eq("user_id", user_id)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data
    return float(rows[0]["weight_kg"]) if rows else None


def delete_latest_weight_log(user_id: str, client: Optional[Client] = None) -> None:
    client = client or get_client()
    logs = get_weight_logs(user_id, client)
    if not logs:
        return
    latest_id = logs[-1]["id"]
    client.table("weight_logs").delete().eq("id", latest_id).execute()
