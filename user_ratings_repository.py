"""user_ratingsテーブル(Supabase/Postgres)へ接続し、レーティングのCRUDを行う。

【Supabase上の user_ratings テーブル構成】
    user_id         : uuid (PK)
    rating          : float8 (現在のレーティング)
    previous_rating : float8 (1回前の更新時点でのレーティング。増減表示用、任意)
    updated_at      : timestamptz (自動記録)

did_replace成功率のみで計算する(クイズの正誤は含めない。design.md参照)。

【使い方】
    from user_ratings_repository import get, update
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

DEFAULT_RATING = 1200  # AtCoderの初期レーティングに倣う


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


def get(user_id: str, client: Optional[Client] = None) -> float:
    """そのユーザーの現在のレーティングを返す。記録が無ければ初期値を返す。"""
    client = client or get_client()
    response = (
        client.table("user_ratings")
        .select("rating")
        .eq("user_id", user_id)
        .execute()
    )
    rows = response.data
    return float(rows[0]["rating"]) if rows else DEFAULT_RATING


def get_rank(user_id: str, client: Optional[Client] = None) -> tuple[int, int]:
    """全ユーザー中の順位(1位が最高)と、全体の人数を返す。

    他人の名前や詳細は一切扱わず、数字の比較だけで順位を出す
    (他人の情報を無断で見せない、というこのアプリの方針に沿う。design.md参照)。
    まだ記録が無いユーザーはDEFAULT_RATINGとして順位に含める。
    """
    client = client or get_client()
    response = client.table("user_ratings").select("user_id, rating").execute()
    ratings = {row["user_id"]: float(row["rating"]) for row in response.data}

    if user_id not in ratings:
        ratings[user_id] = DEFAULT_RATING

    sorted_ratings = sorted(ratings.values(), reverse=True)
    rank = sorted_ratings.index(ratings[user_id]) + 1
    return rank, len(ratings)


def get_all(client: Optional[Client] = None) -> list[dict]:
    """全ユーザーのレーティングを返す(リーダーボード用)。まだ記録が無いユーザーは含まない。"""
    client = client or get_client()
    response = client.table("user_ratings").select("user_id, rating").execute()
    return response.data


def get_previous(user_id: str, client: Optional[Client] = None) -> Optional[float]:
    """前回の更新前のレーティングを返す(記録が無ければNone。画面での増減表示用)。"""
    client = client or get_client()
    response = (
        client.table("user_ratings")
        .select("previous_rating")
        .eq("user_id", user_id)
        .execute()
    )
    rows = response.data
    if not rows or rows[0]["previous_rating"] is None:
        return None
    return float(rows[0]["previous_rating"])


def update(
    user_id: str,
    new_rating: float,
    previous_rating: Optional[float] = None,
    client: Optional[Client] = None,
) -> None:
    """レーティングを更新する(無ければ新規作成、あれば上書き)。

    previous_ratingには、更新前の値(呼び出し側が更新直前に取得したget()の値)を渡す。
    これを一緒に保存しておくことで、画面側で前回からの増減(例: +15)を表示できる。
    """
    client = client or get_client()
    data = {"user_id": user_id, "rating": new_rating}
    if previous_rating is not None:
        data["previous_rating"] = previous_rating
    client.table("user_ratings").upsert(data).execute()


RATING_LABELS = {
    "grey": "灰",
    "brown": "茶",
    "green": "緑",
    "cyan": "水色",
    "blue": "青",
    "yellow": "黄",
    "orange": "橙",
    "red": "赤",
}


def rating_label(rating: float) -> str:
    """色だけに頼らず、色の名前を文字でも伝える(色覚の個人差への配慮)。"""
    return RATING_LABELS[rating_color(rating)]


def rating_color(rating: float) -> str:
    """AtCoderのレーティング色に倣った色分け。"""
    if rating < 400:
        return "grey"
    if rating < 800:
        return "brown"
    if rating < 1200:
        return "green"
    if rating < 1600:
        return "cyan"
    if rating < 2000:
        return "blue"
    if rating < 2400:
        return "yellow"
    if rating < 2800:
        return "orange"
    return "red"
