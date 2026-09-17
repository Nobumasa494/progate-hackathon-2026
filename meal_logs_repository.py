"""meal_logsテーブル（Supabase/Postgres）へ接続し、食事ログのCRUDを行う。

【Supabase上の meal_logs テーブル構成】
    user_id                   : uuid (PK, auth.users(id)への外部キー)
    dish_name                 : text (検索した料理名。機能1への入力と同じ)
    suggested_replacement_name : text (AIが提案したレシピ。機能1の出力)
    original_calories         : int4 (元の料理の推定カロリー。機能1の出力)
    replacement_calories      : int4 (置き換え料理の推定カロリー。機能1の出力)
    did_replace               : bool (実際に置き換えたかどうか)
    actual_calories           : int4 (実際に摂取したカロリー)
    calorie_diff              : int4 (original_calories - actual_calories。このログでの削減量)
    created_at                : timestamp (自動記録)

【使い方】
    from meal_logs_repository import fetch_logs, insert_log, fetch_weekly_summary
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
    """ .env ファイルから環境変数（SUPABASE_URL, SUPABASE_KEY）を読み込む。 """
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


def insert_log(
    user_id: str,
    dish_name: str,
    suggested_replacement_name: str,
    original_calories: int,
    replacement_calories: int,
    did_replace: bool,
    actual_calories: int,
    goal_id: Optional[int] = None,
    client: Optional[Client] = None,
) -> dict:
    """食事ログを1件追加する。calorie_diff は original - actual で自動計算する。

    仕様:
        - did_replace=True（置き換えた）  → actual_calories は replacement 側の値を指定
        - did_replace=False（我慢した）    → actual_calories は original 側の値（=削減なし、差分0）を指定
        - goal_id: 記録した時点でアクティブだった目標のID。目標ごとの進捗集計に使う（機能連携 設計書 10章参照）
    """
    client = client or get_client()
    calorie_diff = original_calories - actual_calories
    resp = (
        client.table("meal_logs")
        .insert(
            {
                "user_id": user_id,
                "dish_name": dish_name,
                "suggested_replacement_name": suggested_replacement_name,
                "original_calories": original_calories,
                "replacement_calories": replacement_calories,
                "did_replace": did_replace,
                "actual_calories": actual_calories,
                "calorie_diff": calorie_diff,
                "goal_id": goal_id,
            }
        )
        .execute()
    )
    return resp.data[0]


def fetch_logs(
    user_id: str,
    client: Optional[Client] = None,
    limit: int = 50,
    order_desc: bool = True,
) -> list:
    """user_id の食事ログを新しい順に取得する。"""
    client = client or get_client()
    query = (
        client.table("meal_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=order_desc)
        .limit(limit)
    )
    resp = query.execute()
    return resp.data


def fetch_weekly_summary(
    user_id: str,
    client: Optional[Client] = None,
) -> list:
    """宴位単位（週単位）のカロリー削減積算を返す。

    元のSQL（Supabaseで実装済みのものと同等）:
        select date_trunc('week', logged_at) as week,
               sum(calorie_diff) as total_saved_kcal
        from meal_logs
        where user_id = auth.uid()
        group by 1
        order by 1 desc;

    注意:
        Supabase Pythonクライアントは group by が直接使えないため、
        全件取得してPython側で週ごとに合計する方式にしている。
        大規模にならなければ十分動作する。
    """
    client = client or get_client()
    logs = fetch_logs(user_id, client, limit=10000, order_desc=False)

    # 週初め（月曜日）をキーに集計する
    weeks: dict[str, int] = {}
    for log in logs:
        week_start = _week_start(log["created_at"])
        weeks[week_start] = weeks.get(week_start, 0) + int(log["calorie_diff"] or 0)

    # 新しい週順に並べて返す
    summary = [
        {"week": week, "total_saved_kcal": total}
        for week, total in sorted(weeks.items(), reverse=True)
    ]
    return summary


def fetch_total_saved(
    user_id: str,
    goal_id: Optional[int] = None,
    client: Optional[Client] = None,
) -> int:
    """calorie_diffの合計を返す。

    goal_idを指定すると、そのIDが記録されているログだけに絞って合計する
    （＝「今の目標だけの進捗」）。指定しなければ全期間の合計になる。
    """
    client = client or get_client()
    resp = (
        client.table("meal_logs")
        .select("calorie_diff, goal_id")
        .eq("user_id", user_id)
        .execute()
    )
    logs = resp.data
    if goal_id is not None:
        logs = [log for log in logs if log.get("goal_id") == goal_id]
    return sum(int(log["calorie_diff"] or 0) for log in logs)


def delete_log(user_id: str, log_id: int, client: Optional[Client] = None) -> bool:
    """自分の食事ログを1件削除する。削除できたらTrue、見つからなければFalse。

    所有権チェック(.eq("user_id", user_id).eq("id", log_id))を必ず入れる。
    RLSが無効のため、これを忘れると誰の記録でもIDが分かれば消せてしまう。
    """
    client = client or get_client()
    resp = (
        client.table("meal_logs")
        .delete()
        .eq("id", log_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(resp.data)


def _week_start(created_at: str) -> str:
    """created_at（ISO8601）からその週の月曜日の日付（YYYY-MM-DD）を返す。"""
    from datetime import datetime, timedelta

    # "2026-09-10T12:34:56Z" 等から日付を抜き出す
    if created_at and "T" in created_at:
        dt = datetime.fromisoformat(created_at.split("T")[0])
    else:
        dt = datetime.fromisoformat(created_at[:10])
    # Pythonでは月曜日=0。今週の月曜を求める
    monday = dt - timedelta(days=dt.weekday())
    return monday.date().isoformat()