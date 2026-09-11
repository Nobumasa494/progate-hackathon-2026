"""機能2: meal_logs（食事ログ）API - Flask版

【テーブル: meal_logs】（Supabaseに実装済み）
    user_id                   : uuid    (PK, auth.users(id)への外部キー)
    dish_name                 : text    (検索した料理名。機能1への入力と同じ)
    suggested_replacement_name: text    (AIが提案したレシピ。機能1の出力)
    original_calories         : int4    (元の料理の推定カロリー。機能1の出力)
    replacement_calories      : int4    (置き換え料理の推定カロリー。機能1の出力)
    did_replace               : bool    (実際に置き換えたかどうか)
    actual_calories           : int4    (実際に摂取したカロリー)
    calorie_diff              : int4    (original_calories - actual_calories。削減量)
    created_at                : timestamp (自動記録)

【エンドポイント（仮設計）】
    POST /meal_logs                    → 新しい食事ログを追加
    GET  /meal_logs?user_id=...        → ログ一覧（新しい順）
    GET  /meal_logs/weekly-summary?user_id=... → 週単位の削減カロリー積算

【起動方法】
    .venv/bin/python meal_logs_app.py
    → http://127.0.0.1:5001 で起動

【検証方法】
    curl -X POST http://127.0.0.1:5001/meal_logs -H "Content-Type: application/json" \
      -d '{...}'

【現状】
    現在はダミーデータ（辞書）で動作。本番統合時は
    meal_logs_repository.py に差し替える（main.pyのダミーと同じ方針）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)


# ---------------------------------------------------------------------------
# ダミーデータ（ローカル検証用）
# 本番では meal_logs_repository.py 経由でSupabaseから読み書きする
# ---------------------------------------------------------------------------
DUMMY_LOGS: list[dict] = [
    {
        "id": "log-0001",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "dish_name": "かつ丼",
        "suggested_replacement_name": "豆腐ハンバーグ定食",
        "original_calories": 900,
        "replacement_calories": 450,
        "did_replace": True,
        "actual_calories": 450,
        "calorie_diff": 450,  # 900 - 450
        "created_at": "2026-09-08T12:00:00Z",
    },
    {
        "id": "log-0002",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "dish_name": "ペペロンチーノ",
        "suggested_replacement_name": "和風きのこスパゲッティ",
        "original_calories": 700,
        "replacement_calories": 500,
        "did_replace": False,  # 置き換えせず、我慢して食べた
        "actual_calories": 700,
        "calorie_diff": 0,  # 700 - 700
        "created_at": "2026-09-09T12:00:00Z",
    },
    {
        "id": "log-0003",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "dish_name": "ハンバーガー",
        "suggested_replacement_name": "チキンサラダ",
        "original_calories": 550,
        "replacement_calories": 250,
        "did_replace": True,
        "actual_calories": 250,
        "calorie_diff": 300,  # 550 - 250
        "created_at": "2026-09-10T12:00:00Z",
    },
]


# ---------------------------------------------------------------------------
# 検証用: 使い方の表示（ルート）
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """ブラウザで開いたときの案内画面。"""
    return jsonify({
        "api": "meal_logs",
        "endpoints": {
            "POST": "/meal_logs",
            "GET": "/meal_logs?user_id=...",
            "GET 週単位集計": "/meal_logs/weekly-summary?user_id=...",
        },
    })


# ---------------------------------------------------------------------------
# 1. 食事ログを追加（Create）
# ---------------------------------------------------------------------------
@app.route("/meal_logs", methods=["POST"])
def create_meal_log():
    """新しい食事ログを追加する。

    入力パラメータ（JSON）:
        user_id                   : str  (必須)
        dish_name                 : str  (必須。検索した料理名)
        suggested_replacement_name: str  (提案された置き換え料理名)
        original_calories         : int  (必須。元料理のカロリー)
        replacement_calories      : int  (必須。置き換え料理のカロリー)
        did_replace               : bool (必須。置き換えたか。true/false)
        actual_calories           : int  (必須。実際に摂取したカロリー)

    出力（JSON）:
        追加されたログ1件（calorie_diff は original - actual で自動計算）

    使用例:
        content: {
          "user_id": "00000000-0000-0000-0000-000000000001",
          "dish_name": "カレーライス",
          "suggested_replacement_name": "野菜カレー",
          "original_calories": 800,
          "replacement_calories": 500,
          "did_replace": true,
          "actual_calories": 500
        }
        → result: {"calorie_diff": 300, "did_replace": true, ...}
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSONボディが必要です"}), 400

    # 必須フィールドの確認
    required = [
        "user_id",
        "dish_name",
        "original_calories",
        "replacement_calories",
        "did_replace",
        "actual_calories",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"不足しているフィールド: {missing}"}), 400

    original = int(data["original_calories"])
    actual = int(data["actual_calories"])
    calorie_diff = original - actual  # 削減量を自動計算

    new_log = {
        "id": f"log-{uuid.uuid4().hex[:8]}",
        "user_id": data["user_id"],
        "dish_name": data["dish_name"],
        "suggested_replacement_name": data.get("suggested_replacement_name", ""),
        "original_calories": original,
        "replacement_calories": int(data["replacement_calories"]),
        "did_replace": bool(data["did_replace"]),
        "actual_calories": actual,
        "calorie_diff": calorie_diff,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    # ★ 本番統合時: meal_logs_repository.insert_log(**...) に差し替える
    DUMMY_LOGS.append(new_log)

    return jsonify(new_log), 201


# ---------------------------------------------------------------------------
# 2. ログ一覧を取得（Read）
# ---------------------------------------------------------------------------
@app.route("/meal_logs", methods=["GET"])
def list_meal_logs():
    """指定ユーザーの食事ログを新しい順に返す。

    入力パラメータ（クエリ）:
        user_id : str (必須)
        limit   : int (任意。デフォルト50)

    出力（JSON）:
        配列（ログ一覧）
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id が必要です（例: ?user_id=xxx）"}), 400

    # user_id に一致するログのみ取得し、新しい順にソート
    logs = [log for log in DUMMY_LOGS if log["user_id"] == user_id]
    logs.sort(key=lambda x: x["created_at"], reverse=True)

    # ★ 本番統合時: meal_logs_repository.fetch_logs(user_id) に差し替える
    return jsonify(logs)


# ---------------------------------------------------------------------------
# 3. 週単位の削減カロリー積算（集計）
# ---------------------------------------------------------------------------
@app.route("/meal_logs/weekly-summary", methods=["GET"])
def weekly_summary():
    """week単位の削減カロリー積算を返す。

    入力パラメータ（クエリ）:
        user_id : str (必須)

    出力（JSON）:
        配列 [{ "week": "YYYY-MM-DD(月曜日)", "total_saved_kcal": 数値 }]
        新しい週順に並ぶ。

    元のSQL（Supabaseで実装済み）:
        select date_trunc('week', logged_at) as week,
               sum(calorie_diff) as total_saved_kcal
        from meal_logs
        where user_id = auth.uid()
        group by 1
        order by 1 desc;
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id が必要です（例: ?user_id=xxx）"}), 400

    # 該当ユーザーのログ
    logs = [log for log in DUMMY_LOGS if log["user_id"] == user_id]

    # 週の開始日（月曜日）ごとに合計する
    week_totals: dict[str, int] = {}
    for log in logs:
        week_start = _week_start(log["created_at"])
        week_totals[week_start] = week_totals.get(week_start, 0) + log["calorie_diff"]

    # 新しい週順にソートして返す
    summary = [
        {"week": week, "total_saved_kcal": total}
        for week, total in sorted(week_totals.items(), reverse=True)
    ]

    # ★ 本番統合時: meal_logs_repository.fetch_weekly_summary(user_id) に差し替える
    return jsonify(summary)


# ---------------------------------------------------------------------------
# テスト用フォーム（ブラウザでパラメータをいじれる）
# 起動後: http://127.0.0.1:5001/test
# ---------------------------------------------------------------------------
@app.route("/test", methods=["GET"])
def test_form():
    """ブラウザ上でパラメータを入力・実行できるテスト画面を表示する。

    使い方:
        1. http://127.0.0.1:5001/test を開く
        2. 「食事ログを追加」欄でパラメータを自由に変更して「追加する」を押す
        3. user_id を入れて「一覧を取得」や「週単位集計」も試せる
    """
    html = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>meal_logs テスト画面</title>
<style>
  body { font-family: sans-serif; margin: 24px; background: #f7f7f7; }
  h1 { font-size: 20px; }
  h2 { font-size: 16px; margin-top: 28px; border-bottom: 2px solid #ccc; padding-bottom: 6px; }
  .card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  label { display: block; margin-top: 8px; font-size: 13px; color: #555; }
  input, select { width: 260px; padding: 6px; margin-top: 2px; border: 1px solid #ccc; border-radius: 4px; }
  button { margin-top: 12px; padding: 8px 20px; background: #4a90d9; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
  button:hover { background: #357abd; }
  pre { background: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; padding: 12px; overflow: auto; font-size: 13px; }
  .note { font-size: 12px; color: #999; }
</style>
</head>
<body>
<h1>meal_logs API テスト画面</h1>

<div class="card">
  <h2>1. 食事ログを追加（POST /meal_logs）</h2>
  <label>user_id <input id="p_user_id" value="00000000-0000-0000-0000-000000000001"></label>
  <label>dish_name（元の料理名） <input id="p_dish_name" value="カレーライス"></label>
  <label>suggested_replacement_name（提案された料理名） <input id="p_repl_name" value="野菜カレー"></label>
  <label>original_calories（元のカロリー） <input id="p_orig" type="number" value="800"></label>
  <label>replacement_calories（置き換えカロリー） <input id="p_repl" type="number" value="500"></label>
  <label>did_replace（置き換えたか） 
    <select id="p_did_replace">
      <option value="true">true（置き換えた）</option>
      <option value="false">false（我慢した）</option>
    </select>
  </label>
  <label>actual_calories（実際に摂取したカロリー） <input id="p_actual" type="number" value="500"></label>
  <br>
  <button onclick="addLog()">追加する</button>
</div>

<div class="card">
  <h2>2. ログ一覧（GET /meal_logs）</h2>
  <label>user_id <input id="g_user_id" value="00000000-0000-0000-0000-000000000001"></label>
  <br>
  <button onclick="listLogs()">一覧を取得</button>
</div>

<div class="card">
  <h2>3. 週単位の削減カロリー（GET /meal_logs/weekly-summary）</h2>
  <label>user_id <input id="s_user_id" value="00000000-0000-0000-0000-000000000001"></label>
  <br>
  <button onclick="weeklySummary()">週単位集計を取得</button>
</div>

<div class="card">
  <h2>結果</h2>
  <pre id="result">ここに結果が表示されます</pre>
</div>

<script>
async function request(method, url, body) {
  const opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  const data = await res.json();
  document.getElementById("result").textContent =
    res.status + " " + method + " " + url + "\\n" + JSON.stringify(data, null, 2);
}

function addLog() {
  const body = {
    user_id: document.getElementById("p_user_id").value,
    dish_name: document.getElementById("p_dish_name").value,
    suggested_replacement_name: document.getElementById("p_repl_name").value,
    original_calories: parseInt(document.getElementById("p_orig").value),
    replacement_calories: parseInt(document.getElementById("p_repl").value),
    did_replace: document.getElementById("p_did_replace").value === "true",
    actual_calories: parseInt(document.getElementById("p_actual").value),
  };
  request("POST", "/meal_logs", body);
}

function listLogs() {
  const user_id = document.getElementById("g_user_id").value;
  request("GET", "/meal_logs?user_id=" + encodeURIComponent(user_id));
}

function weeklySummary() {
  const user_id = document.getElementById("s_user_id").value;
  request("GET", "/meal_logs/weekly-summary?user_id=" + encodeURIComponent(user_id));
}
</script>
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# 週の開始日（月曜日）を計算するヘルパー
# ---------------------------------------------------------------------------
def _week_start(created_at: str) -> str:
    """created_at からその週の月曜日の日付（YYYY-MM-DD）を返す。"""
    if created_at and "T" in created_at:
        dt = datetime.fromisoformat(created_at.split("T")[0])
    else:
        dt = datetime.fromisoformat(created_at[:10])
    monday = dt - timedelta(days=dt.weekday())
    return monday.date().isoformat()


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("meal_logs API を http://127.0.0.1:5001 で起動します")
    print("検証: curl -X POST http://127.0.0.1:5001/meal_logs -H 'Content-Type: application/json' -d '{...}'")
    app.run(host="127.0.0.1", port=5001, debug=True)