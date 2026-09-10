"""機能3: Goals（目標管理）API

エンドポイント:
    GET  /goals/latest?user_id=...  → 最新目標 + target_daily_reduction_kcal
    POST /goals                      → 新しい目標を追加
    POST /goals/calculate            → JSON入力からdaily_reduction_kcalを計算（ローカル検証用）

起動:
    uvicorn goals_api:app --reload --port 8002
    ブラウザ: http://localhost:8002/docs
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from target_calculation import enrich_goal, remaining_days, parse_date

# FastAPIアプリを作成（titleとversionはSwagger UIに表示される）
app = FastAPI(title="Goals API", version="0.1.0")


# ---------------------------------------------------------------------------
# ダミーデータ（ローカル検証用）
# 本番環境では goal_repository.py 経由でSupabaseから取得する
# ダミーのままロジックを組み、統合時に goal_repository に差し替える
# ---------------------------------------------------------------------------
DUMMY_GOALS: dict[str, dict] = {
    "00000000-0000-0000-0000-000000000001": {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "current_weight_kg": 75.0,   # 現在の体重（kg）
        "target_weight_kg": 65.0,    # 目標の体重（kg）
        "target_date": "2026-10-10", # 目標達成の期日
    },
    "00000000-0000-0000-0000-000000000002": {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "current_weight_kg": 60.0,
        "target_weight_kg": 55.0,
        "target_date": "2026-12-31",
    },
}


# ---------------------------------------------------------------------------
# リクエストボディ（APIに送信するJSONの型を定義）
# Pydanticが自動でバリデーションしてくれる
# ---------------------------------------------------------------------------
class GoalCreateRequest(BaseModel):
    """POST /goals で受け取るJSONの型"""
    user_id: str              # ユーザーID
    current_weight_kg: float  # 現在の体重（kg）
    target_weight_kg: float   # 目標の体重（kg）
    target_date: str          # 目標の期日（"2026-10-10" 形式）


class CalculateRequest(BaseModel):
    """POST /goals/calculate で受け取るJSONの型"""
    current_weight_kg: float  # 現在の体重（kg）
    target_weight_kg: float   # 目標の体重（kg）
    target_date: str          # 目標の期日（"2026-10-10" 形式）


# ---------------------------------------------------------------------------
# エンドポイント（URLの窓口となる関数）
# ---------------------------------------------------------------------------

# --- GET: 目標を取得する ---
@app.get("/goals/latest")
def get_latest_goal(user_id: str = Query(..., description="ユーザーID")):
    """指定ユーザーの最新目標を返す。

    例: GET /goals/latest?user_id=00000000-0000-0000-0000-000000000001

    返すJSONには target_daily_reduction_kcal（1日あたりの目標削減カロリー）が含まれる。
    例: (75.0 - 65.0) * 7200 / 30日 = 2400.0 kcal
    """
    # ダミーデータからuser_idをキーにして目標を検索
    goal = DUMMY_GOALS.get(user_id)
    if goal is None:
        # 該当ユーザーがいなければ404エラーを返す
        raise HTTPException(status_code=404, detail="Goal not found")

    # enrich_goal で target_daily_reduction_kcal を計算して付与する
    result = enrich_goal(goal)
    return result


# --- POST: 目標を新規作成する ---
@app.post("/goals")
def create_goal(req: GoalCreateRequest):
    """新しい目標を追加する。

    例: POST /goals
    送信JSON: {"user_id": "xxx", "current_weight_kg": 75, "target_weight_kg": 65, "target_date": "2026-10-10"}

    本番環境ではSupabaseのgoalsテーブルに新しい行を追加する。
    現在はダミーデータの辞書に保存している。
    """
    # リクエストから目標データを組み立てる
    new_goal = {
        "user_id": req.user_id,
        "current_weight_kg": req.current_weight_kg,
        "target_weight_kg": req.target_weight_kg,
        "target_date": req.target_date,
    }
    # ダミーデータに保存（本番では goal_repository.insert_goal() を呼ぶ）
    DUMMY_GOALS[req.user_id] = new_goal

    # 作成した目標に target_daily_reduction_kcal を付与して返す
    result = enrich_goal(new_goal)
    return {"message": "Goal created", "goal": result}


# --- POST: カロリー削減量だけ計算する（テスト用） ---
@app.post("/goals/calculate")
def calculate_daily_reduction(req: CalculateRequest):
    """JSON入力から daily_reduction_kcal を計算して返す（ローカル検証用）。

    例: POST /goals/calculate
    送信JSON: {"current_weight_kg": 75, "target_weight_kg": 65, "target_date": "2026-10-10"}
    返り値: {"target_daily_reduction_kcal": 2400.0, "remaining_days": 30}

    user_idは不要。計算結果だけ確認したいときに使う。
    """
    # 計算用の目标データを組み立てる
    goal = {
        "current_weight_kg": req.current_weight_kg,
        "target_weight_kg": req.target_weight_kg,
        "target_date": req.target_date,
    }

    # enrich_goalで target_daily_reduction_kcal を計算
    result = enrich_goal(goal)

    # 計算結果と残り日数を返す
    return {
        "target_daily_reduction_kcal": result["target_daily_reduction_kcal"],
        "remaining_days": remaining_days(parse_date(req.target_date)),
    }