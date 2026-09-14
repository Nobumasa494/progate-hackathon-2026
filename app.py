"""統合後のエントリーポイント。

機能1(main.py)・機能2(meal_logs_app.py)・機能3(goals_api.py)・機能4(weight_tracking.py)を
1つのFlaskアプリにまとめたもの。画面(HTML)・APIともにここから配信する。

起動:
    python app.py
    → http://127.0.0.1:8000 で起動
"""

from __future__ import annotations

import os
from functools import wraps

from flask import Flask, jsonify, redirect, request, session

import auth_service
import goal_repository
import latest_suggestions
import meal_logs_repository
import radio_episode_repository
import radio_service
import recipe_service
import voicevox_client
import weight_repository

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ["FLASK_SECRET_KEY"]


def require_login_page(view):
    """画面(HTML)用: ログインしていなければ /login に飛ばす。"""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapper


def require_login_api(view):
    """API用: ログインしていなければ401を返す。"""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "ログインが必要です"}), 401
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# 認証(サインアップ・ログイン・ログアウト)
# ---------------------------------------------------------------------------
@app.route("/signup", methods=["GET"])
def page_signup():
    return app.send_static_file("signup.html")


@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    favorite_things = data.get("favorite_things", "")
    if not email or not password:
        return jsonify({"error": "email と password が必要です"}), 400

    try:
        user = auth_service.sign_up(email, password, favorite_things)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if user is None:
        return jsonify({"error": "登録に失敗しました"}), 400

    session["user_id"] = user.id
    return jsonify({"status": "ok"}), 201


@app.route("/login", methods=["GET"])
def page_login():
    return app.send_static_file("login.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "email と password が必要です"}), 400

    try:
        user = auth_service.sign_in(email, password)
    except Exception:
        return jsonify({"error": "メールアドレスまたはパスワードが違います"}), 401

    session["user_id"] = user.id
    return jsonify({"status": "ok"})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/profile", methods=["GET"])
@require_login_page
def page_profile():
    return app.send_static_file("profile.html")


@app.route("/profile/data", methods=["GET"])
@require_login_api
def get_profile_data():
    profile = auth_service.get_profile(session["user_id"])
    return jsonify({
        "favorite_things": profile.get("favorite_things", ""),
        "interests": profile.get("interests", ""),
        "voice_a_id": profile.get("voice_a_id", voicevox_client.DEFAULT_SPEAKER_A),
        "voice_b_id": profile.get("voice_b_id", voicevox_client.DEFAULT_SPEAKER_B),
    })


@app.route("/profile/data", methods=["POST"])
@require_login_api
def update_profile_data():
    data = request.get_json(silent=True) or {}
    auth_service.update_profile(
        session["user_id"],
        favorite_things=data.get("favorite_things", ""),
        interests=data.get("interests", ""),
        voice_a_id=int(data["voice_a_id"]),
        voice_b_id=int(data["voice_b_id"]),
    )
    return jsonify({"status": "ok"})


@app.route("/radio/voices", methods=["GET"])
@require_login_api
def radio_voices():
    return jsonify(voicevox_client.list_speakers())


# ---------------------------------------------------------------------------
# 画面(HTML)
# ---------------------------------------------------------------------------
@app.route("/")
@require_login_page
def page_home():
    return app.send_static_file("home.html")


@app.route("/recipe")
@require_login_page
def page_recipe():
    return app.send_static_file("index.html")


@app.route("/record")
@require_login_page
def page_record():
    return app.send_static_file("record.html")


@app.route("/goals")
@require_login_page
def page_goals():
    return app.send_static_file("goals.html")


@app.route("/weight-log")
@require_login_page
def page_weight():
    return app.send_static_file("weight.html")


@app.route("/radio")
@require_login_page
def page_radio():
    return app.send_static_file("radio.html")


# ---------------------------------------------------------------------------
# 機能1: レシピ提案
# ---------------------------------------------------------------------------
@app.route("/suggest", methods=["GET"])
@require_login_api
def suggest():
    dish_name = request.args.get("dish_name")
    user_id = session["user_id"]
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
@require_login_api
def suggestions_latest():
    user_id = session["user_id"]
    suggestion = latest_suggestions.get_latest_suggestion(user_id)
    if suggestion is None:
        return jsonify({"error": "まだ提案がありません"}), 404
    return jsonify(suggestion)


# ---------------------------------------------------------------------------
# 機能2: 食事ログ
# ---------------------------------------------------------------------------
@app.route("/meal_logs", methods=["POST"])
@require_login_api
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

    diary_note = data.get("diary_note", "").strip()
    if not diary_note:
        return jsonify({"error": "今日、DJたちに教えたいことを入力してください"}), 400

    user_id = session["user_id"]

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
    # 食事ログを書くタイミングで一緒に記録してもらうことで、書き忘れを防ぐ
    # (以前はラジオ画面に別の入力欄があったが、そちらは廃止した)
    auth_service.update_pending_diary_note(user_id, diary_note)
    radio_service.maybe_generate_in_background(user_id)
    return jsonify(log), 201


@app.route("/meal_logs", methods=["GET"])
@require_login_api
def list_meal_logs():
    user_id = session["user_id"]
    logs = meal_logs_repository.fetch_logs(user_id)
    return jsonify(logs)


@app.route("/meal_logs/weekly-summary", methods=["GET"])
@require_login_api
def meal_logs_weekly_summary():
    user_id = session["user_id"]
    summary = meal_logs_repository.fetch_weekly_summary(user_id)
    return jsonify(summary)


@app.route("/progress", methods=["GET"])
@require_login_api
def get_progress():
    """目標ごとの進捗(機能連携 設計書 10章)。

    current_goal_saved_kcal: 今の目標を立ててから、食事ログで削減できた合計
    all_time_saved_kcal    : 目標が変わっても関係ない、通算の削減合計
    remaining_kcal         : 今の目標まであといくつ削減が必要か(体重ではなく食事ログの実績ベース)
    """
    user_id = session["user_id"]
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
@require_login_api
def get_latest_goal():
    user_id = session["user_id"]
    goal = goal_repository.get_latest_goal_with_daily_reduction(user_id)
    if goal is None:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal)


@app.route("/goals", methods=["POST"])
@require_login_api
def create_goal():
    data = request.get_json(silent=True) or {}
    required = ["target_weight_kg", "target_date"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"不足しているフィールド: {missing}"}), 400

    user_id = session["user_id"]

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
@require_login_api
def record_weight():
    user_id = session["user_id"]
    weight_kg = request.args.get("weight_kg", type=float)
    if weight_kg is None:
        return jsonify({"error": "weight_kg が必要です"}), 400
    weight_repository.insert_weight_log(user_id, weight_kg)
    return jsonify({"status": "ok"})


@app.route("/weight", methods=["GET"])
@require_login_api
def list_weight():
    user_id = session["user_id"]
    return jsonify(weight_repository.get_weight_logs(user_id))


@app.route("/weight/latest", methods=["DELETE"])
@require_login_api
def delete_latest_weight():
    user_id = session["user_id"]
    weight_repository.delete_latest_weight_log(user_id)
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# 深夜ラジオ機能(実験中)
# ---------------------------------------------------------------------------
@app.route("/radio/latest", methods=["GET"])
@require_login_api
def radio_latest():
    user_id = session["user_id"]
    episode = radio_episode_repository.fetch_latest_episode(user_id)
    if episode is None or not episode.get("storage_path"):
        return jsonify({"episode": None})

    audio_url = radio_episode_repository.get_audio_url(episode["storage_path"])
    return jsonify({
        "episode": {
            "id": episode["id"],
            "created_at": episode["created_at"],
            "script": episode["script"],
            "is_saved": episode["is_saved"],
            "is_shared": episode.get("is_shared", False),
            "shared_display_name": episode.get("shared_display_name"),
            "shared_comment": episode.get("shared_comment"),
            "audio_url": audio_url,
        }
    })


@app.route("/radio/status", methods=["GET"])
@require_login_api
def radio_status():
    user_id = session["user_id"]
    return jsonify({
        "generating": radio_service.is_generating(user_id),
        "has_episode_today": radio_service.has_episode_today(user_id),
        "reached_daily_limit": radio_service.reached_daily_limit(user_id),
    })


@app.route("/radio/generate", methods=["POST"])
@require_login_api
def radio_generate():
    user_id = session["user_id"]
    if radio_service.reached_daily_limit(user_id):
        return jsonify({"error": f"1日に生成できる回数({radio_service.MAX_EPISODES_PER_DAY}回)に達しています"}), 429
    episode = radio_service.generate_todays_episode(user_id)
    return jsonify({"status": "ok", "episode_id": episode["id"]})


@app.route("/radio/share", methods=["POST"])
@require_login_api
def radio_share():
    data = request.get_json(silent=True) or {}
    episode_id = data.get("episode_id")
    if not episode_id:
        return jsonify({"error": "episode_id が必要です"}), 400
    display_name = data.get("display_name", "").strip()[:30]
    comment = data.get("comment", "").strip()[:200]
    radio_episode_repository.mark_shared(session["user_id"], episode_id, display_name, comment)
    return jsonify({"status": "ok"})


@app.route("/discover")
@require_login_page
def page_discover():
    return app.send_static_file("discover.html")


@app.route("/discover/feed", methods=["GET"])
@require_login_api
def discover_feed():
    before = request.args.get("before")
    episodes = radio_episode_repository.fetch_shared_episodes(limit=10, before=before)
    result = []
    for ep in episodes:
        if not ep.get("storage_path"):
            continue
        result.append({
            "id": ep["id"],
            "created_at": ep["created_at"],
            "script": ep["script"],
            "audio_url": radio_episode_repository.get_audio_url(ep["storage_path"]),
            "display_name": ep.get("shared_display_name") or "匿名",
            "comment": ep.get("shared_comment") or "",
        })
    return jsonify({"episodes": result})


if __name__ == "__main__":
    # デバッグモードは事故で本番に持ち込まないよう、明示的に環境変数で有効化した時だけONにする。
    # 開発中に使いたい場合は FLASK_DEBUG=1 を .env に設定する。
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=8000, debug=debug_mode)
