"""統合後のエントリーポイント。

機能1(main.py)・機能2(meal_logs_app.py)・機能3(goals_api.py)・機能4(weight_tracking.py)を
1つのFlaskアプリにまとめたもの。画面(HTML)・APIともにここから配信する。

起動:
    python app.py
    → http://127.0.0.1:8000 で起動
"""

from __future__ import annotations

from flask import Flask, jsonify, request

import goal_repository
import latest_suggestions
import meal_logs_repository
import recipe_service
import weight_repository

# 認証機能がまだ無いため、ローカル検証用の固定ユーザーIDを既定値にする
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

app = Flask(__name__, static_folder="static", static_url_path="")


# ---------------------------------------------------------------------------
# 画面(HTML)
# ---------------------------------------------------------------------------
@app.route("/")
def page_recipe():
    return app.send_static_file("index.html")


@app.route("/record")
def page_record():
    return app.send_static_file("record.html")


@app.route("/goals")
def page_goals():
    return app.send_static_file("goals.html")


@app.route("/weight-log")
def page_weight():
    return app.send_static_file("weight.html")


# ---------------------------------------------------------------------------
# 機能1: レシピ提案
# ---------------------------------------------------------------------------
@app.route("/suggest", methods=["GET"])
def suggest():
    dish_name = request.args.get("dish_name")
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    if not dish_name:
        return jsonify({"error": "dish_name が必要です"}), 400

    # 機能3の目標を踏まえた提案にする（未設定・期日切れなら通常の提案にフォールバック）
    goal = goal_repository.get_latest_goal_with_daily_reduction(user_id)
    target = None
    if goal and not goal.get("expired") and goal.get("target_daily_reduction_kcal"):
        target = goal["target_daily_reduction_kcal"]

    result = recipe_service.suggest_replacement(dish_name, target_daily_reduction_kcal=target)

    # 機能2が後で使えるように、最新の提案として保存しておく
    latest_suggestions.save_latest_suggestion(user_id, {
        "dish_name": result["original_dish"],
        "suggested_replacement_name": result["replacement_name"],
        "original_calories": result["original_calories"],
        "replacement_calories": result["replacement_calories"],
        "ingredients": result["ingredients"],
        "steps": result["steps"],
        "estimated_cost_yen": result["estimated_cost_yen"],
    })

    return jsonify(result)


@app.route("/suggestions/latest", methods=["GET"])
def suggestions_latest():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    suggestion = latest_suggestions.get_latest_suggestion(user_id)
    if suggestion is None:
        return jsonify({"error": "まだ提案がありません"}), 404
    return jsonify(suggestion)


# ---------------------------------------------------------------------------
# 機能2: 食事ログ
# ---------------------------------------------------------------------------
@app.route("/meal_logs", methods=["POST"])
def create_meal_log():
    data = request.get_json(silent=True) or {}
    required = [
        "dish_name",
        "original_calories",
        "replacement_calories",
        "did_replace",
        "actual_calories",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"不足しているフィールド: {missing}"}), 400

    user_id = data.get("user_id", DEFAULT_USER_ID)

    # 記録した時点でアクティブな目標のIDを一緒に保存しておく（目標ごとの進捗集計に使う）
    current_goal = goal_repository.fetch_latest_goal(user_id)
    goal_id = current_goal["id"] if current_goal else None

    log = meal_logs_repository.insert_log(
        user_id=user_id,
        dish_name=data["dish_name"],
        suggested_replacement_name=data.get("suggested_replacement_name", ""),
        original_calories=int(data["original_calories"]),
        replacement_calories=int(data["replacement_calories"]),
        did_replace=bool(data["did_replace"]),
        actual_calories=int(data["actual_calories"]),
        goal_id=goal_id,
    )
    return jsonify(log), 201


@app.route("/meal_logs", methods=["GET"])
def list_meal_logs():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    logs = meal_logs_repository.fetch_logs(user_id)
    return jsonify(logs)


@app.route("/meal_logs/weekly-summary", methods=["GET"])
def meal_logs_weekly_summary():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    summary = meal_logs_repository.fetch_weekly_summary(user_id)
    return jsonify(summary)


@app.route("/progress", methods=["GET"])
def get_progress():
    """目標ごとの進捗(機能連携 設計書 10章)。

    current_goal_saved_kcal: 今の目標を立ててから、食事ログで削減できた合計
    all_time_saved_kcal    : 目標が変わっても関係ない、通算の削減合計
    remaining_kcal         : 今の目標まであといくつ削減が必要か(体重ではなく食事ログの実績ベース)
    """
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    current_goal = goal_repository.fetch_latest_goal(user_id)  # 生データ(体重は目標作成時点で固定)
    current_goal_id = current_goal["id"] if current_goal else None

    saved = meal_logs_repository.fetch_total_saved(user_id, goal_id=current_goal_id)
    all_time_saved = meal_logs_repository.fetch_total_saved(user_id)

    remaining = None
    if current_goal:
        goal_total_kcal = (
            float(current_goal["current_weight_kg"]) - float(current_goal["target_weight_kg"])
        ) * 7200
        remaining = goal_total_kcal - saved

    return jsonify({
        "current_goal_saved_kcal": saved,
        "all_time_saved_kcal": all_time_saved,
        "remaining_kcal": remaining,
    })


# ---------------------------------------------------------------------------
# 機能3: 目標
# ---------------------------------------------------------------------------
@app.route("/goals/latest", methods=["GET"])
def get_latest_goal():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    goal = goal_repository.get_latest_goal_with_daily_reduction(user_id)
    if goal is None:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal)


@app.route("/goals", methods=["POST"])
def create_goal():
    data = request.get_json(silent=True) or {}
    required = ["target_weight_kg", "target_date"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"不足しているフィールド: {missing}"}), 400

    user_id = data.get("user_id", DEFAULT_USER_ID)

    # 現在の体重は入力させず、体重記録(機能4)の最新値を自動で使う
    current_weight_kg = weight_repository.get_latest_weight(user_id)
    if current_weight_kg is None:
        return jsonify({"error": "先に体重を記録してください"}), 400

    goal_repository.insert_goal(
        user_id=user_id,
        current_weight_kg=current_weight_kg,
        target_weight_kg=float(data["target_weight_kg"]),
        target_date=data["target_date"],
    )

    result = goal_repository.get_latest_goal_with_daily_reduction(user_id)
    return jsonify({"message": "Goal created", "goal": result}), 201


# ---------------------------------------------------------------------------
# 機能4: 体重記録
# ---------------------------------------------------------------------------
@app.route("/weight", methods=["POST"])
def record_weight():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    weight_kg = request.args.get("weight_kg", type=float)
    if weight_kg is None:
        return jsonify({"error": "weight_kg が必要です"}), 400
    weight_repository.insert_weight_log(user_id, weight_kg)
    return jsonify({"status": "ok"})


@app.route("/weight", methods=["GET"])
def list_weight():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    return jsonify(weight_repository.get_weight_logs(user_id))


@app.route("/weight/latest", methods=["DELETE"])
def delete_latest_weight():
    user_id = request.args.get("user_id", DEFAULT_USER_ID)
    weight_repository.delete_latest_weight_log(user_id)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
