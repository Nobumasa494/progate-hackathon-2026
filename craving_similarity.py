"""提案の多様性チェックで使う、Embeddings関連の共通処理。

- 料理名・提案内容をベクトル化する
- ベクトル同士の近さを計算する
- ユーザーの過去の提案履歴から、意味的に近いものを検索する(RAG的な検索)
- 履歴から、よく使われている主な食材を抽出する

「今困っていないことのために部品を増やさない」方針に従い、pgvectorは使わず、
その都度Pythonで全件取得して比較する(データ規模が数千件を超えたら再検討)。
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from openai import OpenAI

import suggestion_history_repository as history_repo


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()
        load_dotenv(Path(__file__).with_name(".env"))


_load_env()

_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

EMBEDDING_MODEL = "text-embedding-3-small"
HISTORY_WINDOW = 5


def get_embedding(text: str) -> list[float]:
    resp = _client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return resp.data[0].embedding


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b)


def build_text(name: str, ingredients: list[dict], steps: list[str]) -> str:
    """提案全体(名前+材料+手順)を、Embeddings比較用の1つの文章にまとめる。"""
    ingredients_text = "、".join(f"{i['name']}{i['amount']}" for i in ingredients)
    steps_text = "。".join(steps)
    return f"{name}。材料: {ingredients_text}。手順: {steps_text}"


def search_similar(user_id: str, query_embedding: list[float], limit: int = HISTORY_WINDOW) -> list[dict]:
    """dish_nameの完全一致ではなく、意味的に近い過去の提案履歴を検索する(RAG)。

    今のデータ規模(1ユーザーあたり多くても数十件)ではpgvectorのような
    専用インデックスは不要なため、全件取得してPython側でスコアリングする。
    """
    all_history = history_repo.get_all(user_id)
    scored = [
        (item, cosine_similarity(query_embedding, item["embedding"]))
        for item in all_history
        if item.get("embedding")
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _score in scored[:limit]]


def extract_main_ingredients(history: list[dict]) -> list[str]:
    """履歴から、材料名(重複除去)を抽出する。避けるべき食材の指示に使う。"""
    names: list[str] = []
    for item in history:
        for ingredient in item.get("ingredients", []):
            name = ingredient.get("name")
            if name and name not in names:
                names.append(name)
    return names
