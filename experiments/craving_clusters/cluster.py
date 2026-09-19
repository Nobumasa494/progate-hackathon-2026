"""個人プロトタイプ: meal_logsのdish_nameをEmbeddingsでベクトル化し、K-meansでジャンル分けする。

本体(app.py等)には組み込まれていない、検証用の使い捨てスクリプト。
実行方法:
    python3 experiments/craving_clusters/cluster.py
"""

from __future__ import annotations

import os
import sys

# リポジトリのルートをパスに追加し、既存のrepositoryモジュールを再利用する
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from openai import OpenAI
from sklearn.cluster import KMeans

import meal_logs_repository as m

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def fetch_all_dish_names() -> list[str]:
    """全ユーザーのdish_nameを取得する(プロトタイプなのでuser_idは絞らない)。"""
    supabase = m.get_client()
    resp = supabase.table("meal_logs").select("dish_name").execute()
    return [row["dish_name"] for row in resp.data if row["dish_name"]]


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """OpenAI Embeddings APIで、料理名のリストをベクトルのリストに変換する。"""
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in resp.data]


def main() -> None:
    dish_names = fetch_all_dish_names()
    print(f"取得した料理名: {len(dish_names)}件")
    print(dish_names)

    if len(dish_names) < 4:
        print("料理名が少なすぎるので、クラスタリングは行いません。")
        return

    embeddings = get_embeddings(dish_names)
    print(f"Embeddings取得完了: {len(embeddings)}件、次元数={len(embeddings[0])}")

    k = 3
    kmeans = KMeans(n_clusters=k, random_state=0, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    print("\n--- クラスタリング結果 ---")
    clusters: dict[int, list[str]] = {}
    for dish_name, label in zip(dish_names, labels):
        clusters.setdefault(int(label), []).append(dish_name)

    for cluster_id, names in clusters.items():
        print(f"\nクラスタ{cluster_id}: {names}")


if __name__ == "__main__":
    main()
