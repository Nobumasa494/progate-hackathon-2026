"""suggestion_historyテーブル(Supabase/Postgres)へ接続し、提案履歴のCRUDを行う。

【Supabase上の suggestion_history テーブル構成】
    id          : int8 (PK, 自動採番)
    user_id     : uuid
    dish_name   : text (検索された元の料理名)
    ingredients : jsonb (提案された材料)
    steps       : jsonb (提案された手順)
    embedding   : jsonb (提案全体をEmbeddings化したベクトル、float配列)
    created_at  : timestamptz (自動記録)

【使い方】
    from suggestion_history_repository import save, get_all
"""

from __future__ import annotations

import os
import threading
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

_client: Client | None = None
_client_lock = threading.Lock()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    """Supabaseクライアントを取得する。未指定時は環境変数から読む。

    他のrepositoryファイルと同じく、モジュールレベルでクライアントを
    キャッシュして使い回す(メモリリーク対策。CLAUDE.md参照)。
    """
    global _client
    if url is None and key is None:
        if _client is None:
            with _client_lock:
                if _client is None:
                    _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        return _client
    return create_client(url or os.environ["SUPABASE_URL"], key or os.environ["SUPABASE_KEY"])


def save(
    user_id: str,
    dish_name: str,
    ingredients: list[dict],
    steps: list[str],
    embedding: list[float],
    client: Optional[Client] = None,
) -> None:
    """提案を1件保存する。記録(meal_logs)の有無に関係なく、生成のたびに呼ぶ。"""
    client = client or get_client()
    client.table("suggestion_history").insert({
        "user_id": user_id,
        "dish_name": dish_name,
        "ingredients": ingredients,
        "steps": steps,
        "embedding": embedding,
    }).execute()


def get_all(user_id: str, client: Optional[Client] = None) -> list[dict]:
    """そのユーザーの提案履歴を全件返す(RAG検索の材料にする)。"""
    client = client or get_client()
    response = (
        client.table("suggestion_history")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return response.data
