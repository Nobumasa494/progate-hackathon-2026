"""discoveriesテーブル(Supabase/Postgres)へ接続し、「探すクエスト」の発見報告のCRUDを行う。

【Supabase上の discoveries テーブル構成】
    id         : int8 (PK, 自動採番)
    user_id    : uuid
    dish_name  : text (発見した食材名)
    store_name : text (発見した店名)
    lat        : float8 (緯度)
    lng        : float8 (経度)
    photo_url  : text (発見証拠の写真URL、Supabase Storage連携)
    comment    : text (一言コメント、任意)
    is_pioneer : bool (半径PIONEER_RADIUS_METERS以内に既存の発見報告が無ければ true。「開拓者」バッジ判定用)
    created_at : timestamptz (自動記録)

参考: docs/search_quest/README.md

【使い方】
    from discovery_repository import save, get_by_dish
"""

from __future__ import annotations

import math
import os
import threading
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

import uuid

from supabase import Client, create_client

BUCKET = "discovery-photos"  # 公開バケット(みんなが見られる発見報告の写真)

# 「開拓者」バッジ判定の半径。店名の表記ゆれ(全角/半角・省略など)は文字列
# 一致では拾いきれないため、位置(緯度経度)の近さで同一店舗とみなす。
PIONEER_RADIUS_METERS = 50


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


def upload_photo(user_id: str, photo_bytes: bytes, content_type: str, client: Optional[Client] = None) -> str:
    """発見証拠の写真をStorageにアップロードし、公開URLを返す。"""
    client = client or get_client()
    ext = "jpg" if "jpeg" in content_type or "jpg" in content_type else "png"
    storage_path = f"{user_id}/{uuid.uuid4()}.{ext}"
    client.storage.from_(BUCKET).upload(storage_path, photo_bytes, {"content-type": content_type})
    return client.storage.from_(BUCKET).get_public_url(storage_path)


def _distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2地点間の距離(メートル)をhaversine公式で概算する。"""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_new_store(lat: float, lng: float, client: Optional[Client] = None) -> bool:
    """半径PIONEER_RADIUS_METERS以内に既存の発見報告が無いか(=開拓者バッジの対象か)を返す。

    店名の文字列一致ではなく位置の近さで判定することで、店名の表記ゆれ
    (「イオン渋谷店」「ｲｵﾝ渋谷店」「イオン渋谷駅前店」等)に左右されない。
    """
    client = client or get_client()
    resp = client.table("discoveries").select("lat, lng").execute()
    return not any(
        _distance_meters(lat, lng, row["lat"], row["lng"]) <= PIONEER_RADIUS_METERS
        for row in resp.data
    )


def save(
    user_id: str,
    dish_name: str,
    store_name: str,
    lat: float,
    lng: float,
    photo_url: str,
    comment: Optional[str] = None,
    is_pioneer: bool = False,
    client: Optional[Client] = None,
) -> dict:
    """発見報告を1件保存する。"""
    client = client or get_client()
    resp = client.table("discoveries").insert({
        "user_id": user_id,
        "dish_name": dish_name,
        "store_name": store_name,
        "lat": lat,
        "lng": lng,
        "photo_url": photo_url,
        "comment": comment,
        "is_pioneer": is_pioneer,
    }).execute()
    return resp.data[0]


def count_pioneer_badges(client: Optional[Client] = None) -> dict[str, int]:
    """ユーザーごとの開拓者バッジ数(is_pioneer=trueの件数)を返す(リーダーボード用)。"""
    client = client or get_client()
    resp = client.table("discoveries").select("user_id").eq("is_pioneer", True).execute()
    counts: dict[str, int] = {}
    for row in resp.data:
        counts[row["user_id"]] = counts.get(row["user_id"], 0) + 1
    return counts


def get_by_dish(dish_name: str, client: Optional[Client] = None) -> list[dict]:
    """指定した食材の発見報告を全件返す(地図にピンを立てるのに使う。食材で絞って表示する)。

    他ユーザーの情報を無断で見せないという方針(design.md参照)に沿い、
    user_idは含めず、地図表示に必要な列だけを返す。
    """
    client = client or get_client()
    resp = (
        client.table("discoveries")
        .select("id, store_name, lat, lng, photo_url, comment, is_pioneer, created_at")
        .eq("dish_name", dish_name)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data
