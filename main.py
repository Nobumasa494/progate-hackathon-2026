import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PROMPT = """\
あなたは管理栄養士のアシスタントです。
ユーザーが「食べたい料理名」を入力するので、以下の条件を満たす置き換えレシピを1つ提案してください。

- 元の料理の推定カロリーを算出する
- カロリーを抑えつつ、できるだけ満足感が近い置き換えレシピを考える
- 材料は家庭で手に入りやすいものにする
- 手順は3ステップ以内で簡潔にする
- 出力は必ず以下のJSON形式のみで返す。説明文や前置きは一切つけない。

{
  "original_dish": "string",
  "original_calories": number,
  "replacement_name": "string",
  "ingredients": [{"name": "string", "amount": "string"}],
  "steps": ["string"],
  "replacement_calories": number,
  "calorie_diff": number,
  "estimated_cost_yen": number
}
"""


def suggest_replacement(dish_name: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"料理名: {dish_name}"},
        ],
    )
    result = json.loads(response.choices[0].message.content)
    result["calorie_diff"] = result["original_calories"] - result["replacement_calories"]
    return result


app = Flask(__name__, static_folder="static", static_url_path="")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/suggest", methods=["GET"])
def suggest():
    dish_name = request.args.get("dish_name")
    return jsonify(suggest_replacement(dish_name))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
