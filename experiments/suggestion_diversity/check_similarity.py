"""個人プロトタイプ: 同じ料理名で2回提案を出し、どれくらい似ているかを数字で確認する。

Step 1: まずは「本当に似た提案が返ってくるのか」を実測するだけのスクリプト。
本体には組み込まれていない、使い捨ての検証用コード。

実行方法:
    python3 experiments/suggestion_diversity/check_similarity.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

import recipe_service

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def embed(text: str) -> list[float]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return resp.data[0].embedding


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


def main() -> None:
    dish_name = "ラーメン"

    print(f"「{dish_name}」で2回、提案を生成します...")
    result1 = recipe_service.suggest_replacement(dish_name)
    result2 = recipe_service.suggest_replacement(dish_name)

    print("\n--- 提案1 ---")
    print("名前:", result1["replacement_name"])
    print("材料:", result1["ingredients"])
    print("手順:", result1["steps"])

    print("\n--- 提案2 ---")
    print("名前:", result2["replacement_name"])
    print("材料:", result2["ingredients"])
    print("手順:", result2["steps"])

    # 「中身」として、名前+材料+手順をまとめたテキストで比較する
    def full_text(result: dict) -> str:
        ingredients_text = "、".join(f"{i['name']}{i['amount']}" for i in result["ingredients"])
        steps_text = "。".join(result["steps"])
        return f"{result['replacement_name']}。材料: {ingredients_text}。手順: {steps_text}"

    text1 = full_text(result1)
    text2 = full_text(result2)

    vec1 = embed(text1)
    vec2 = embed(text2)

    similarity = cosine_similarity(vec1, vec2)
    print(f"\n--- 類似度 ---\n{similarity:.4f} (1に近いほど似ている、0に近いほど似ていない)")


if __name__ == "__main__":
    main()
