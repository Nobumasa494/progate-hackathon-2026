"""quiz_resultsテーブル(Supabase/Postgres)へ接続し、栄養豆知識クイズの回答結果を保存する。

【Supabase上の quiz_results テーブル構成】
    id         : int8 (PK, 自動採番)
    user_id    : uuid
    question   : text (出題内容)
    is_correct : bool (正誤)
    created_at : timestamptz (自動記録)

レーティング機能には使わない、独立した機能(design.md参照)。

【使い方】
    from quiz_results_repository import save
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
    """Supabaseクライアントを取得する。未指定時は環境変数から読む(他repositoryと同じパターン)。"""
    global _client
    if url is None and key is None:
        if _client is None:
            with _client_lock:
                if _client is None:
                    _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        return _client
    return create_client(url or os.environ["SUPABASE_URL"], key or os.environ["SUPABASE_KEY"])


def save(user_id: str, question: str, is_correct: bool, client: Optional[Client] = None) -> None:
    client = client or get_client()
    client.table("quiz_results").insert({
        "user_id": user_id,
        "question": question,
        "is_correct": is_correct,
    }).execute()
