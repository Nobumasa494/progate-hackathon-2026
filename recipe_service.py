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
- カロリーを抑えることより先に、「これは美味しそう、食べたい」と思えることを最優先にする。
  カロリーが低いだけで味気ない置き換え(単に量を減らす、味付けを薄くするだけ 等)は避ける
- 満足感(食べ応え・味の濃さ・香ばしさなど)を落とさない、むしろ「これもアリだな」と思える具体的な工夫
  (香辛料・香味野菜・焼き色・とろみ 等の具体的な調理の工夫)を1つ以上入れる
- 別の料理に変えてもよいが、まずは元の料理の見た目・食感・味の系統にできるだけ近いものを優先する
  (例: かつ丼→全く違う和え物ではなく、同じ「揚げ物+ご飯+甘辛だれ」の構成を保ったまま置き換える)。
  近づけるのが難しい場合のみ、大きく違う料理に置き換えてよい
- 「主食を低カロリー食材に置き換えるだけ」(麺→こんにゃく麺、ご飯→カリフラワーライス 等)のような、
  ダイエットレシピとして最もありきたりで想像しやすいパターンだけで終わらせない。
  それを軸にする場合でも、+αの工夫(スープのコクを出す・香ばしさを足す・トッピングを加える 等)を
  必ず組み合わせ、「置き換えたのに、むしろ手が込んでいて美味しそう」と思わせる
- 元の料理を特徴づける要素(ラーメンなら煮卵・海苔・背脂のコクなど)を最低1つは再現する工夫を入れ、
  「別物になった」ではなく「ちゃんと元の料理の代わりになっている」と感じられるようにする
- 材料は家庭で手に入りやすいものにする
- 手順は3ステップ以内で簡潔にする
- 同じ料理名でも毎回同じ提案に偏らないよう、次のうちどれを軸にするかをランダムに選んでから考える:
  (a) 主な食材を低カロリーな別の食材に置き換える (b) 調理法を変える(揚げる→焼く/蒸す 等)
  (c) 主食の量や種類を調整する (d) 全体の構成を変えてボリュームで満足感を出す
- 提案する料理(元の料理または置き換え後の料理)に関連した、意外性のある栄養豆知識を1つ、
  3択クイズの形で作る(質問文・選択肢3つ・その中の正解を1つ)
- 出力は必ず以下のJSON形式のみで返す。説明文や前置きは一切つけない。

{
  "original_dish": "string",
  "original_calories": number,
  "replacement_name": "string",
  "ingredients": [{"name": "string", "amount": "string"}],
  "steps": ["string"],
  "replacement_calories": number,
  "calorie_diff": number,
  "estimated_cost_yen": number,
  "trivia_question": "string",
  "trivia_choices": ["string", "string", "string"],
  "trivia_answer": "string"
}
"""


def suggest_replacement(
    dish_name: str,
    target_daily_reduction_kcal: Optional[float] = None,
    allergens: Optional[list[str]] = None,
    avoid_ingredients: Optional[list[str]] = None,
) -> dict:
    """置き換えレシピを提案する。

    target_daily_reduction_kcal が指定されていれば（＝機能3で目標が設定されていれば）、
    それを踏まえた提案になるようAIへの指示文に反映する。

    allergens に特定原材料（えび・カシューナッツ・かに・くるみ・小麦・そば・卵・乳・落花生）
    のいずれかを含むと、その食材を使ったレシピをAIが提案しなくなる。

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

    avoid_instruction = ""
    if avoid_ingredients:
        avoid_instruction = (
            f"\nこの人への過去の提案では、{'・'.join(avoid_ingredients)}を使っています。"
            "今回はこれらを使わずに考えてください。"
        )

    allergen_instruction = ""
    if allergens:
        allergen_instruction = (
            "\n以下の食材はアレルギーのため絶対に使用しないでください: "
            + "、".join(allergens)
            + "\nアレルゲンを含む調味料・加工食品も使わないでください。"
        )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        temperature=1.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + extra_instruction + allergen_instruction + avoid_instruction},
            {"role": "user", "content": f"料理名: {dish_name}"},
        ],
    )
    result = json.loads(response.choices[0].message.content)
    result["calorie_diff"] = result["original_calories"] - result["replacement_calories"]
    result["target_daily_reduction_kcal_used"] = used_target
    result["is_capped"] = is_capped
    return result
