"""goalsテーブル（Supabase/Postgres）へ接続し、目標のCRUDを行う。

【Supabase上の goals テーブル構成】
    user_id           : uuid  (PK, auth.users(id)への外部キー)
    current_weight_kg : numeric (目標設定時点の体重)
    target_weight_kg  : numeric (目標の体重)
    target_date       : date    (「いつまでに」の期日)
    created_at        : timestamp (自動で記録される作成日時)

【使い方】
    from goal_repository import fetch_latest_goal, insert_goal

【メモ】
    - 統合のタイミングで main.py から import して使う
    - 今は goal_repository を直接使わず、main.py のダミーデータで検証OK
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# python-dotenv が入っていなくてもエラーにならないようにする
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from supabase import Client, create_client

from target_calculation import enrich_goal


def _load_env() -> None:
    """ .env ファイルから環境変数（SUPABASE_URL, SUPABASE_KEY）を読み込む。

    .env ファイルの例:
        SUPABASE_URL=https://xxxxx.supabase.co
        SUPABASE_KEY=eyJhbGciOi...
    """
    if load_dotenv is not None:
        # プロジェクトルートの .env を読む
        load_dotenv()
        # goal_repository.py と同じディレクトリの .env も読む
        load_dotenv(Path(__file__).with_name(".env"))


# モジュール読み込み時に .env を自動で読み込む
_load_env()


def get_client(url: Optional[str] = None, key: Optional[str] = None) -> Client:
    """Supabaseクライアントを作成する。

    引数未指定時は環境変数から自動で読む:
        SUPABASE_URL → SupabaseプロジェクトのURL
        SUPABASE_KEY → anon key または service_role key
    """
    url = url or os.environ["SUPABASE_URL"]
    key = key or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def fetch_latest_goal(
    user_id: str, client: Optional[Client] = None
) -> Optional[dict]:
    """指定ユーザーの最新goal1件を返す。無ければNone。

    Supabaseへのクエリ内容:
        1. goalsテーブルから user_id が一致する行を探す
        2. created_at（作成日時）の降順でソート（新しい順）
        3. 先頭1件だけ取得
    """
    client = client or get_client()
    resp = (
        client.table("goals")          # goalsテーブルを指定
        .select("*")                   # 全カラムを取得
        .eq("user_id", user_id)        # user_idが一致する行だけ
        .order("created_at", desc=True)  # 新しい順にソート
        .limit(1)                      # 1件だけ取得
        .execute()                     # クエリを実行
    )
    rows = resp.data  # 結果はリスト型（例: [{"user_id": "...", ...}]）
    return rows[0] if rows else None   # 1件目を返す or 見つからなければNone


def get_latest_goal_with_daily_reduction(
    user_id: str, client: Optional[Client] = None
) -> Optional[dict]:
    """最新goalを取得し、target_daily_reduction_kcal を付与して返す。

    処理の流れ:
        1. fetch_latest_goal でSupabaseから最新の目標を取得
        2. enrich_goal で target_daily_reduction_kcal を計算して追加
    """
    goal = fetch_latest_goal(user_id, client)
    if goal is None:
        return None  # 目標がなければNoneを返す
    return enrich_goal(goal)  # 計算結果を付与して返す


def insert_goal(
    user_id: str,
    current_weight_kg: float,
    target_weight_kg: float,
    target_date: str,
    client: Optional[Client] = None,
) -> dict:
    """新しい目標行をSupabaseに追加し、追加したレコードを返す。

    仕様: 目標を更新するたびに新しい行を追加する（上書きしない）。
    これにより、目標の履歴が残る。
    """
    client = client or get_client()
    resp = (
        client.table("goals")          # goalsテーブルを指定
        .insert(                       # 新しい行を追加
            {
                "user_id": user_id,
                "current_weight_kg": current_weight_kg,
                "target_weight_kg": target_weight_kg,
                "target_date": target_date,
            }
        )
        .execute()                     # クエリを実行
    )
    return resp.data[0]  # 追加されたレコードを返す
