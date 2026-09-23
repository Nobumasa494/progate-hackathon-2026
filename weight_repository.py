"""weight_logsテーブル（Supabase/Postgres）へ接続し、体重記録のCRUDを行う。

【Supabase上の weight_logs テーブル構成】
    id         : integer (PK, 自動採番)
    user_id    : uuid (auth.users(id)への外部キー)
    weight_kg  : numeric (記録した体重)
    step_count : integer (その日の歩数、2026-09頃追加)
    created_at : timestamp (記録した日付。日付単位で1行=1日、upsert)

【使い方】
    from weight_repository import upsert_weight_log, get_weight_logs, get_latest_weight
    """

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional
from datetime import date, datetime, timedelta, timezone

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





def upsert_weight_log(
    user_id: str,
    weight_kg: float,
    log_date: date,
    step_count: Optional[int] = None,
    client: Optional[Client] = None,
) -> None:
    """指定した日付の体重を記録する。

    同じ日付の記録が既にあれば、その値を上書きする(置き換え)。
    無ければ、その日付で新しい行を追加する。

    step_count はその日の歩数。None なら「指定なし」として扱い、
    既存行を更新する場合は step_count を変更しない(誤って消さないため)。
    """
    client = client or get_client()
    start = datetime.combine(log_date, datetime.min.time())
    end = start + timedelta(days=1)

    existing = (
        client.table("weight_logs")
        .select("id")
        .eq("user_id", user_id)
        .gte("created_at", start.isoformat())
        .lt("created_at", end.isoformat())
        .execute()
    )
    rows = existing.data

    if rows:
        target_id = rows[0]["id"]
        update_fields = {"weight_kg": weight_kg}
        if step_count is not None:
            update_fields["step_count"] = step_count
        client.table("weight_logs").update(update_fields).eq("id", target_id).execute()
    else:
        values = {
            "user_id": user_id,
            "weight_kg": weight_kg,
            "created_at": start.isoformat(),
            "step_count": step_count if step_count is not None else 0,
        }
        client.table("weight_logs").insert(values).execute()

def get_weight_logs(user_id: str, client: Optional[Client] = None) -> list[dict]:
    """そのユーザーの体重記録を、記録した順（古い順）に返す。"""
    client = client or get_client()
    response = (
        client.table("weight_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return response.data

def delete_weight_log_by_date(
    user_id: str, log_date: date, client: Optional[Client] = None
) -> None:
    """指定した日付の体重記録を削除する(その日の記録が無ければ何もしない)。"""
    client = client or get_client()
    start = datetime.combine(log_date, datetime.min.time())
    end = start + timedelta(days=1)

    client.table("weight_logs").delete().eq("user_id", user_id).gte(
        "created_at", start.isoformat()
    ).lt("created_at", end.isoformat()).execute()


def fetch_weekly_steps(user_id: str, client: Optional[Client] = None) -> int:
    """そのユーザーの今週(月曜起点)の歩数の合計を返す。

    meal_logs_repository の週集計と同じく、プロセス内で全件取得してPythonで
    集計する(1ユーザーあたりのデータ量が小さく、週の境界をDB側に任せない
    方が境界条件の扱いが揃うため)。
    """
    client = client or get_client()
    response = (
        client.table("weight_logs")
        .select("step_count, created_at")
        .eq("user_id", user_id)
        .execute()
    )

    this_week = _week_start(datetime.now(timezone.utc).isoformat())
    total = 0
    for row in response.data:
        if row.get("step_count") is None:
            continue
        if _week_start(row["created_at"]) != this_week:
            continue
        total += int(row["step_count"])
    return total


def _week_start(created_at: str) -> str:
    """created_at(ISO8601)からその週の月曜日の日付(YYYY-MM-DD)を返す。

    meal_logs_repository の _week_start と同じ挙動。週起点の集計の
    基準を揃えるため、ここにも同名で持つ。
    """
    from datetime import datetime, timedelta

    if created_at and "T" in created_at:
        dt = datetime.fromisoformat(created_at.split("T")[0])
    else:
        dt = datetime.fromisoformat(created_at[:10])
    monday = dt - timedelta(days=dt.weekday())
    return monday.date().isoformat()


def get_latest_weight(user_id: str, client: Optional[Client] = None) -> Optional[float]:
    """そのユーザーの最新の体重（kg）を返す。記録が無ければNone。

    goal_repository が「現在の体重」として使う値はここから取得する。
    """
    client = client or get_client()
    response = (
        client.table("weight_logs")
        .select("weight_kg")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data
    return float(rows[0]["weight_kg"]) if rows else None


