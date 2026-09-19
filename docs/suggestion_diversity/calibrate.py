"""個人プロトタイプ: 類似度の「ものさし」を作る。

- 全く同じ文章同士 → 上限の基準
- 明らかに違う料理(ラーメン vs ケーキ)の提案同士 → 下限の基準
この2つと、前回測った「ラーメンの提案1 vs 提案2」(0.7684)を並べて比較する。

実行方法:
    python3 experiments/suggestion_diversity/calibrate.py
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


def full_text(result: dict) -> str:
    ingredients_text = "、".join(f"{i['name']}{i['amount']}" for i in result["ingredients"])
    steps_text = "。".join(result["steps"])
    return f"{result['replacement_name']}。材料: {ingredients_text}。手順: {steps_text}"


def main() -> None:
    # 基準1: 全く同じ文章同士(上限の基準)
    same_text = "豆腐と野菜の旨辛ラーメン。材料: 蒟蒻麺1袋、木綿豆腐100g。手順: 茹でて混ぜる。"
    vec_a = embed(same_text)
    vec_b = embed(same_text)
    upper_bound = cosine_similarity(vec_a, vec_b)
    print(f"【上限の基準】全く同じ文章同士: {upper_bound:.4f}")

    # 基準2: 明らかに違う料理(ラーメン vs ケーキ)の提案同士(下限の基準)
    print("\nラーメンとケーキで、それぞれ提案を1回ずつ生成します...")
    ramen_result = recipe_service.suggest_replacement("ラーメン")
    cake_result = recipe_service.suggest_replacement("ケーキ")

    ramen_text = full_text(ramen_result)
    cake_text = full_text(cake_result)
    vec_ramen = embed(ramen_text)
    vec_cake = embed(cake_text)
    lower_bound = cosine_similarity(vec_ramen, vec_cake)
    print(f"【下限の基準】ラーメン提案 vs ケーキ提案: {lower_bound:.4f}")

    print("\n--- まとめ ---")
    print(f"同じ文章同士(上限)   : {upper_bound:.4f}")
    print(f"ラーメンの提案1 vs 2  : 0.7684 (前回測定)")
    print(f"ラーメン vs ケーキ(下限): {lower_bound:.4f}")


if __name__ == "__main__":
    main()
