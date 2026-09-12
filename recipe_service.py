"""機能1: 料理名から置き換えレシピをAIに提案してもらう。

main.py（旧・機能1単体アプリ）から、OpenAI呼び出し部分だけを切り出したもの。
app.py（統合後）から import して使う。
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from target_calculation import MAX_SAFE_DAILY_REDUCTION_KCAL

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


def suggest_replacement(
    dish_name: str,
    target_daily_reduction_kcal: Optional[float] = None,
) -> dict:
    """置き換えレシピを提案する。

    target_daily_reduction_kcal が指定されていれば（＝機能3で目標が設定されていれば）、
    それを踏まえた提案になるようAIへの指示文に反映する。

    安全のため、AIに伝える削減目標は MAX_SAFE_DAILY_REDUCTION_KCAL を上限に丸める。
    本来の目標が上限を超えていた場合は is_capped=True を結果に含め、
    ユーザーに「安全な範囲に抑えて提案している」ことを隠さず伝える。
    """
    extra_instruction = ""
    used_target = None
    is_capped = False

    if target_daily_reduction_kcal:
        used_target = min(target_daily_reduction_kcal, MAX_SAFE_DAILY_REDUCTION_KCAL)
        is_capped = used_target < target_daily_reduction_kcal
        extra_instruction = (
            f"\nこの人は1日あたり{used_target}kcalの削減を目標にしています。"
            "それを踏まえた提案にしてください。"
        )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + extra_instruction},
            {"role": "user", "content": f"料理名: {dish_name}"},
        ],
    )
    result = json.loads(response.choices[0].message.content)
    result["calorie_diff"] = result["original_calories"] - result["replacement_calories"]
    result["target_daily_reduction_kcal_used"] = used_target
    result["is_capped"] = is_capped
    return result
