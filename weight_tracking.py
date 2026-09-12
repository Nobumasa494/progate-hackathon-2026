import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


def insert_weight_log(user_id: str, weight_kg: float) -> None:
    supabase.table("weight_logs").insert({
        "user_id": user_id,
        "weight_kg": weight_kg,
    }).execute()


def get_weight_logs(user_id: str) -> list[dict]:
    response = (
        supabase.table("weight_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("id")
        .execute()
    )
    return response.data


def delete_latest_weight_log(user_id: str) -> None:
    logs = get_weight_logs(user_id)
    if not logs:
        return
    latest_id = logs[-1]["id"]
    supabase.table("weight_logs").delete().eq("id", latest_id).execute()


app = Flask(__name__, static_folder="static_weight", static_url_path="")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/weight", methods=["POST"])
def record_weight():
    user_id = request.args.get("user_id")
    weight_kg = request.args.get("weight_kg", type=float)
    if not user_id or weight_kg is None:
        return jsonify({"error": "user_id と weight_kg が必要です"}), 400
    insert_weight_log(user_id, weight_kg)
    return jsonify({"status": "ok"})


@app.route("/weight", methods=["GET"])
def list_weight():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id が必要です"}), 400
    return jsonify(get_weight_logs(user_id))


@app.route("/weight/latest", methods=["DELETE"])
def delete_latest_weight():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id が必要です"}), 400
    delete_latest_weight_log(user_id)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)
