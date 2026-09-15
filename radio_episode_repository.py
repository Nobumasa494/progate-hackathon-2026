"""radio_episodesテーブル（Supabase/Postgres）とSupabase Storageへ接続し、
深夜ラジオ機能(実験中)のエピソードのCRUDを行う。

【Supabase上の radio_episodes テーブル構成】
    id           : uuid (PK)
    user_id      : uuid (auth.users(id)への外部キー)
    created_at   : timestamptz (自動記録)
    script       : text (その回の台本テキスト。継続性のため次回生成時に読む)
    storage_path : text (音声ファイルの保存先。Storageから削除したらNullに戻す)
    is_saved     : boolean (未使用。以前は「ずっと残す」機能があったが廃止した)
    is_shared    : boolean (ユーザーが「みんなに共有する」を選んだかどうか)
    shared_display_name : text (共有時に本人が自由に決める表示名。実名ではない任意項目)
    shared_comment       : text (共有時に本人が添えるひとこと)

【Storageのバケット】
    radio-audio (非公開)

【使い方】
    from radio_episode_repository import generate_and_store_episode, fetch_latest_episode
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from supabase import Client, create_client

BUCKET = "radio-audio"

# 1人が同時に保持できるエピソードの上限。共有されているかどうかは関係なく、
# これを超えたら一番古いものから音声・台本ごと完全に削除する(共有時の表示名・コメントも
# 行ごと一緒に消える)。上限は他ユーザーの活動と無関係に、本人の生成回数だけで決まる。
MAX_EPISODES_PER_USER = 2

# アプリ全体で保持するエピソード数の絶対上限。Supabase無料枠のStorage容量(約1GB)を
# 音声1件あたりの実サイズ(5分・24kHz・モノラルWAVで約14MB)から逆算した値。
# 本人ごとの上限だけだとユーザー数が増えた分だけ際限なく増えるため、
# 容量そのものに直結した最終防衛ラインとして別に設ける。
MAX_TOTAL_EPISODES = 80


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()

_client: Client | None = None
_client_lock = threading.Lock()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    """Supabaseクライアントを取得する。未指定時は環境変数から読む。

    毎回create_client()し直すと、呼ぶたびに新しいHTTP接続プールが作られ、
    使い終わってもすぐには解放されない。/radio/statusなど数秒おきにポーリングされる
    エンドポイントで積み重なり、本番でメモリ超過による再起動が繰り返し起きる原因に
    なっていたため、環境変数からのデフォルト呼び出し(url/key未指定)の場合は
    モジュール内で1つだけ作って使い回す。_client_lockは、起動直後に複数スレッドが
    ほぼ同時に呼んだ場合に、無駄なクライアントが2重に作られるのを防ぐため。
    """
    global _client
    if url is None and key is None:
        if _client is None:
            with _client_lock:
                if _client is None:
                    _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        return _client
    return create_client(url or os.environ["SUPABASE_URL"], key or os.environ["SUPABASE_KEY"])


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


def delete_old_episodes(user_id: str, keep: int = MAX_EPISODES_PER_USER, client: Optional[Client] = None) -> None:
    """本人ごとに直近keep件だけ残し、それより古い行を完全に削除する。

    is_shared(共有中)かどうかは見ない。共有されていても、この上限を超えれば
    音声・台本ごと削除され、共有時に添えた表示名・コメントも一緒に消える。
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
        1. 新しい音声をStorageにアップロードする
        2. radio_episodesに新しい行を作る(台本・保存先パス)
        3. 本人ごとにMAX_EPISODES_PER_USER件より古い行を削除する
           (共有されているかどうかは関係ない)
        4. アプリ全体でMAX_TOTAL_EPISODES件を超えていたら、ユーザー・共有の別を
           問わず一番古いものから削除する(Storage容量そのものへの安全弁)
    """
    client = client or get_client()

    storage_path = f"{user_id}/{uuid.uuid4()}.wav"
    client.storage.from_(BUCKET).upload(storage_path, audio_bytes, {"content-type": "audio/wav"})

    response = (
        client.table("radio_episodes")
        .insert({"user_id": user_id, "script": script, "storage_path": storage_path})
        .execute()
    )
    episode = response.data[0]

    delete_old_episodes(user_id, client=client)
    _enforce_global_cap(client)

    return episode


def _enforce_global_cap(client: Optional[Client] = None) -> None:
    """アプリ全体のエピソード数がMAX_TOTAL_EPISODESを超えていたら、
    ユーザー・共有の別を問わず、一番古いものから完全に削除する。
    """
    client = client or get_client()
    response = (
        client.table("radio_episodes")
        .select("id, storage_path")
        .order("created_at", desc=True)
        .execute()
    )
    excess_rows = response.data[MAX_TOTAL_EPISODES:]
    for row in excess_rows:
        if row.get("storage_path"):
            delete_episode_audio(row["storage_path"], client)
        client.table("radio_episodes").delete().eq("id", row["id"]).execute()


def get_audio_url(storage_path: str, expires_in: int = 3600, client: Optional[Client] = None) -> str:
    """再生用の一時的なURL(署名付き)を発行する。非公開バケットなので直リンクは使えない。"""
    client = client or get_client()
    result = client.storage.from_(BUCKET).create_signed_url(storage_path, expires_in)
    return result["signedURL"]


def mark_shared(
    user_id: str,
    episode_id: str,
    display_name: str = "",
    comment: str = "",
    client: Optional[Client] = None,
) -> None:
    """「みんなに共有する」が押されたときに呼ぶ。公開フィード(discover)に載る。

    user_idも受け取り、そのユーザー自身のエピソードにしか適用できないようにする(他人のIDを
    指定して勝手に共有状態を変えられないようにするため)。

    display_name・commentは本人が自由に決められる、実名とは無関係な任意項目(6-6章参照)。
    空文字ならNoneとして保存し、discover側で「匿名」として扱う。

    共有した後も、本人がMAX_EPISODES_PER_USER件を超えて生成すれば、他の回と同じように
    通常通り削除される(6-7章参照)。共有専用の猶予は設けていない。
    """
    client = client or get_client()
    client.table("radio_episodes").update({
        "is_shared": True,
        "shared_display_name": display_name or None,
        "shared_comment": comment or None,
    }).eq("id", episode_id).eq("user_id", user_id).execute()


def fetch_shared_episodes(limit: int = 10, before: Optional[str] = None, client: Optional[Client] = None) -> list[dict]:
    """公開フィード用に、共有されたエピソードを新しい順に取得する。

    user_idは意図的に取得しない(誰の投稿か分からない形で返すため、6-6章参照)。
    before(created_atの値)を指定すると、それより古いものから続きを取得する(無限スクロール用)。
    """
    client = client or get_client()
    query = (
        client.table("radio_episodes")
        .select("id, created_at, script, storage_path, shared_display_name, shared_comment")
        .eq("is_shared", True)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if before:
        query = query.lt("created_at", before)
    return query.execute().data
