"""radio_episodesテーブル（Supabase/Postgres）とSupabase Storageへ接続し、
深夜ラジオ機能(実験中)のエピソードのCRUDを行う。

【Supabase上の radio_episodes テーブル構成】
    id           : uuid (PK)
    user_id      : uuid (auth.users(id)への外部キー)
    created_at   : timestamptz (自動記録)
    script       : text (その回の台本テキスト。継続性のため次回生成時に読む)
    storage_path : text (音声ファイルの保存先。Storageから削除したらNullに戻す)
    is_saved     : boolean (ユーザーが「この回を保存する」を選んだかどうか)

【Storageのバケット】
    radio-audio (非公開)

【使い方】
    from radio_episode_repository import generate_and_store_episode, fetch_latest_episode
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from supabase import Client, create_client

BUCKET = "radio-audio"


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    url = url or os.environ["SUPABASE_URL"]
    key = key or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def fetch_latest_episode(user_id: str, client: Optional[Client] = None) -> Optional[dict]:
    """そのユーザーの最新のエピソードを返す。無ければNone。"""
    client = client or get_client()
    response = (
        client.table("radio_episodes")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data
    return rows[0] if rows else None


def count_episodes_since(user_id: str, since_iso: str, client: Optional[Client] = None) -> int:
    """指定した時刻(ISO8601)以降に作られたエピソードの件数を返す(1日の生成回数の上限チェックに使う)。"""
    client = client or get_client()
    response = (
        client.table("radio_episodes")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", since_iso)
        .execute()
    )
    return response.count or 0


def fetch_recent_scripts(user_id: str, limit: int = 3, client: Optional[Client] = None) -> list[str]:
    """直近数回分の台本テキストを、新しい順に返す(継続性のあるプロンプト作りに使う)。"""
    client = client or get_client()
    response = (
        client.table("radio_episodes")
        .select("script")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [row["script"] for row in response.data if row.get("script")]


def delete_episode_audio(storage_path: str, client: Optional[Client] = None) -> None:
    """Storage上の音声ファイルだけを削除する(台本テキストの行は残す)。"""
    client = client or get_client()
    client.storage.from_(BUCKET).remove([storage_path])


def delete_old_episodes(user_id: str, keep: int = 2, client: Optional[Client] = None) -> None:
    """継続性のプロンプトに使う直近keep件を残し、それより古い行を削除する(台本テキストがたまり続けないように)。

    is_saved の行は今は使っていない(6-3章: 保存は端末ダウンロード方式に変更済み)ため、
    古ければ問答無用で削除する。音声はすでに generate_and_store_episode 側で消えている想定だが、
    念のためstorage_pathが残っていれば一緒に削除する。
    """
    client = client or get_client()
    response = (
        client.table("radio_episodes")
        .select("id, storage_path")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    old_rows = response.data[keep:]
    for row in old_rows:
        if row.get("storage_path"):
            delete_episode_audio(row["storage_path"], client)
        client.table("radio_episodes").delete().eq("id", row["id"]).execute()


def generate_and_store_episode(user_id: str, script: str, audio_bytes: bytes, client: Optional[Client] = None) -> dict:
    """新しいエピソードを保存する。

    手順(設計書6-3章):
        1. 前回のエピソードがあり、音声が残っていて、保存指定されていなければ、その音声だけ削除する
        2. 新しい音声をStorageにアップロードする
        3. radio_episodesに新しい行を作る(台本・保存先パス)
        4. 継続性に使う直近2件より古い行を削除する(テキストが際限なくたまらないように)
    """
    client = client or get_client()

    old_episode = fetch_latest_episode(user_id, client)
    if (
        old_episode
        and old_episode.get("storage_path")
        and not old_episode.get("is_saved")
        and not old_episode.get("is_shared")
    ):
        delete_episode_audio(old_episode["storage_path"], client)
        client.table("radio_episodes").update({"storage_path": None}).eq("id", old_episode["id"]).execute()

    storage_path = f"{user_id}/{uuid.uuid4()}.wav"
    client.storage.from_(BUCKET).upload(storage_path, audio_bytes, {"content-type": "audio/wav"})

    response = (
        client.table("radio_episodes")
        .insert({"user_id": user_id, "script": script, "storage_path": storage_path})
        .execute()
    )
    episode = response.data[0]

    delete_old_episodes(user_id, keep=2, client=client)

    return episode


def get_audio_url(storage_path: str, expires_in: int = 3600, client: Optional[Client] = None) -> str:
    """再生用の一時的なURL(署名付き)を発行する。非公開バケットなので直リンクは使えない。"""
    client = client or get_client()
    result = client.storage.from_(BUCKET).create_signed_url(storage_path, expires_in)
    return result["signedURL"]


def mark_saved(episode_id: str, client: Optional[Client] = None) -> None:
    """「この回を保存する」が押されたときに呼ぶ。自動削除の対象から外れる。"""
    client = client or get_client()
    client.table("radio_episodes").update({"is_saved": True}).eq("id", episode_id).execute()


def mark_shared(user_id: str, episode_id: str, client: Optional[Client] = None) -> None:
    """「みんなに共有する」が押されたときに呼ぶ。自動削除の対象から外れ、公開フィードに載る。

    user_idも受け取り、そのユーザー自身のエピソードにしか適用できないようにする(他人のIDを
    指定して勝手に共有状態を変えられないようにするため)。
    """
    client = client or get_client()
    client.table("radio_episodes").update({"is_shared": True}).eq("id", episode_id).eq("user_id", user_id).execute()


def fetch_shared_episodes(limit: int = 10, before: Optional[str] = None, client: Optional[Client] = None) -> list[dict]:
    """公開フィード用に、共有されたエピソードを新しい順に取得する。

    user_idは意図的に取得しない(誰の投稿か分からない形で返すため、6-6章参照)。
    before(created_atの値)を指定すると、それより古いものから続きを取得する(無限スクロール用)。
    """
    client = client or get_client()
    query = (
        client.table("radio_episodes")
        .select("id, created_at, script, storage_path")
        .eq("is_shared", True)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if before:
        query = query.lt("created_at", before)
    return query.execute().data
