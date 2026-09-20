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
SEARCH_MIN_SIMILARITY = 0.4  # これ未満は「関係ない料理」とみなして候補から除外する
# 料理名 vs 料理名で実測: 同一=1.0、表記ゆれ(ラーメン vs 豚骨ラーメン)=0.6365、
# 同ジャンル(ラーメン vs うどん)=0.5312、無関係(ラーメン vs カキフライ)=0.3474。
# 0.35〜0.47の間に明確な境界があったため、0.4を採用した。
MAIN_INGREDIENTS_PER_ITEM = 2  # 1件の履歴から、主な食材として何品まで抽出するか


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

    query_embeddingは「料理名だけ」のベクトルを渡すこと。比較対象も
    dish_name_embedding(料理名だけのベクトル)を使う。提案全体(embedding)と
    比較すると、短い料理名 vs 長いレシピ全文という形の違いのせいで、
    無関係な料理の方が高いスコアになる不具合が実データで見つかったため。
    """
    all_history = history_repo.get_all(user_id)
    scored = [
        (item, cosine_similarity(query_embedding, item["dish_name_embedding"]))
        for item in all_history
        if item.get("dish_name_embedding")
    ]
    # 足切りラインを設けないと、全く関係ない料理(例:「ラーメン」)まで
    # 上位に紛れ込んでしまうことが実データで判明したため、閾値未満は除外する
    scored = [pair for pair in scored if pair[1] >= SEARCH_MIN_SIMILARITY]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _score in scored[:limit]]


def extract_main_ingredients(history: list[dict]) -> list[str]:
    """履歴から、主な食材(重複除去)を抽出する。避けるべき食材の指示に使う。

    材料を全部拾うと、黒胡椒や塩のような、どの料理にも出てくる調味料まで
    「避けてください」に含まれてしまい、本当に避けたい食材(豆腐など)の
    指示がその他大勢に埋もれてAIに無視される、という不具合が実データで
    見つかった。AIの出力は主な食材(豆腐・鶏肉など)を先頭に書く傾向がある
    ため、各履歴の先頭MAIN_INGREDIENTS_PER_ITEM品だけを使うようにした。
    """
    names: list[str] = []
    for item in history:
        for ingredient in item.get("ingredients", [])[:MAIN_INGREDIENTS_PER_ITEM]:
            name = ingredient.get("name")
            if name and name not in names:
                names.append(name)
    return names
