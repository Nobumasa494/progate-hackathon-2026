"""radio_memoriesテーブル(Supabase/Postgres)へ接続し、記憶(milestone/highlight/reflection)のCRUDを行う。

【Supabase上の radio_memories テーブル構成】
    id         : uuid (PK)
    user_id    : uuid (auth.users(id)への外部キー)
    created_at : timestamptz (自動記録)
    content    : text (記憶の文章)
    importance : int (重要度。1〜10の目安)
    kind       : text ("milestone" | "highlight" | "reflection")

【削除の方針(設計書6-4章)】
    milestone  : 削除しない(滅多に発生しないため、ずっと残す)
    highlight・reflection : 種類ごとに直近5件だけ残し、それより古い行は削除する
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

KEEP_PER_KIND = 5


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    url = url or os.environ["SUPABASE_URL"]
    key = key or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def save_memory(user_id: str, content: str, importance: int, kind: str, client: Optional[Client] = None) -> dict:
    """記憶を1件保存する。milestone以外は、保存直後に古い分を自動で削除する。"""
    client = client or get_client()
    response = (
        client.table("radio_memories")
        .insert({"user_id": user_id, "content": content, "importance": importance, "kind": kind})
        .execute()
    )
    if kind != "milestone":
        _delete_old_memories(user_id, kind, keep=KEEP_PER_KIND, client=client)
    return response.data[0]


def _delete_old_memories(user_id: str, kind: str, keep: int, client: Optional[Client] = None) -> None:
    """指定したkindについて、新しい順にkeep件だけ残し、それより古い行を削除する。"""
    client = client or get_client()
    response = (
        client.table("radio_memories")
        .select("id")
        .eq("user_id", user_id)
        .eq("kind", kind)
        .order("created_at", desc=True)
        .execute()
    )
    old_rows = response.data[keep:]
    for row in old_rows:
        client.table("radio_memories").delete().eq("id", row["id"]).execute()


def fetch_recent_memories(user_id: str, limit: int = 15, client: Optional[Client] = None) -> list[dict]:
    """振り返り(reflection)生成のために、種類を問わず新しい順に記憶を取得する。"""
    client = client or get_client()
    response = (
        client.table("radio_memories")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def fetch_top_memories(user_id: str, limit: int = 3, client: Optional[Client] = None) -> list[str]:
    """重要度×新しさのスコアが高い順に、記憶の文章だけを返す(台本生成のプロンプトに渡す用)。"""
    from datetime import datetime, timezone

    client = client or get_client()
    rows = fetch_recent_memories(user_id, limit=30, client=client)  # 候補として少し多めに取得してから絞る
    if not rows:
        return []

    now = datetime.now(timezone.utc)

    def score(row: dict) -> float:
        created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        days = (now - created_at).total_seconds() / 86400
        return row["importance"] / (1 + days)

    rows.sort(key=score, reverse=True)
    return [row["content"] for row in rows[:limit]]
