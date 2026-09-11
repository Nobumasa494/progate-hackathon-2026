"""機能3: Goals（目標管理）API

エンドポイント:
    GET  /goals/latest?user_id=...  → 最新目標 + target_daily_reduction_kcal
    POST /goals                      → 新しい目標を追加
    POST /goals/calculate            → JSON入力からdaily_reduction_kcalを計算（ローカル検証用）

起動:
    python goals_api.py
    → http://127.0.0.1:8002 で起動
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from target_calculation import enrich_goal, remaining_days, parse_date

app = Flask(__name__)


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
# エンドポイント（URLの窓口となる関数）
# ---------------------------------------------------------------------------

# --- GET: 目標を取得する ---
@app.route("/goals/latest", methods=["GET"])
def get_latest_goal():
    """指定ユーザーの最新目標を返す。

    例: GET /goals/latest?user_id=00000000-0000-0000-0000-000000000001

    返すJSONには target_daily_reduction_kcal（1日あたりの目標削減カロリー）が含まれる。
    例: (75.0 - 65.0) * 7200 / 30日 = 2400.0 kcal
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id が必要です（例: ?user_id=xxx）"}), 400

    # ダミーデータからuser_idをキーにして目標を検索
    goal = DUMMY_GOALS.get(user_id)
    if goal is None:
        # 該当ユーザーがいなければ404エラーを返す
        return jsonify({"error": "Goal not found"}), 404

    # enrich_goal で target_daily_reduction_kcal を計算して付与する
    result = enrich_goal(goal)
    return jsonify(result)


# --- POST: 目標を新規作成する ---
@app.route("/goals", methods=["POST"])
def create_goal():
    """新しい目標を追加する。

    例: POST /goals
    送信JSON: {"user_id": "xxx", "current_weight_kg": 75, "target_weight_kg": 65, "target_date": "2026-10-10"}

    本番環境ではSupabaseのgoalsテーブルに新しい行を追加する。
    現在はダミーデータの辞書に保存している。
    """
    data = request.get_json(silent=True) or {}
    required = ["user_id", "current_weight_kg", "target_weight_kg", "target_date"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"不足しているフィールド: {missing}"}), 400

    # リクエストから目標データを組み立てる
    new_goal = {
        "user_id": data["user_id"],
        "current_weight_kg": float(data["current_weight_kg"]),
        "target_weight_kg": float(data["target_weight_kg"]),
        "target_date": data["target_date"],
    }
    # ダミーデータに保存（本番では goal_repository.insert_goal() を呼ぶ）
    DUMMY_GOALS[data["user_id"]] = new_goal

    # 作成した目標に target_daily_reduction_kcal を付与して返す
    result = enrich_goal(new_goal)
    return jsonify({"message": "Goal created", "goal": result}), 201


# --- POST: カロリー削減量だけ計算する（テスト用） ---
@app.route("/goals/calculate", methods=["POST"])
def calculate_daily_reduction():
    """JSON入力から daily_reduction_kcal を計算して返す（ローカル検証用）。

    例: POST /goals/calculate
    送信JSON: {"current_weight_kg": 75, "target_weight_kg": 65, "target_date": "2026-10-10"}
    返り値: {"target_daily_reduction_kcal": 2400.0, "remaining_days": 30}

    user_idは不要。計算結果だけ確認したいときに使う。
    """
    data = request.get_json(silent=True) or {}
    required = ["current_weight_kg", "target_weight_kg", "target_date"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"不足しているフィールド: {missing}"}), 400

    # 計算用の目標データを組み立てる
    goal = {
        "current_weight_kg": float(data["current_weight_kg"]),
        "target_weight_kg": float(data["target_weight_kg"]),
        "target_date": data["target_date"],
    }

    # enrich_goalで target_daily_reduction_kcal を計算
    result = enrich_goal(goal)

    # 計算結果と残り日数を返す
    return jsonify({
        "target_daily_reduction_kcal": result["target_daily_reduction_kcal"],
        "remaining_days": remaining_days(parse_date(data["target_date"])),
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8002, debug=True)
