# 提案の多様性チェック機能

検討・実装日: 2026-09-19
状態: ①(提案の多様性チェック)は実装・動作確認済み。②(クイズ)③(レーティング)は未実装。

このフォルダには検証用スクリプトと設計資料のみを置いている。実際にアプリへ組み込んだ実装本体は、リポジトリルートの[`craving_similarity.py`](../../craving_similarity.py)・[`suggestion_history_repository.py`](../../suggestion_history_repository.py)と、[`app.py`](../../app.py)の`/suggest`ルート・[`recipe_service.py`](../../recipe_service.py)の`suggest_replacement()`にある。

チームとしてこの機能を採用するかはまだ未合意。個人の`experiment/craving-clusters`ブランチで実装済み。

## 背景・動機

- 機能1(置き換え提案)の`SYSTEM_PROMPT`には「同じ料理名でも毎回同じ提案に偏らないように」という指示があるが、実際にAIに任せてみると、豆腐・こんにゃく麺のような「ダイエットレシピの鉄板ネタ」に偏りがちなことを実測で確認した([check_similarity.py](check_similarity.py)参照)。
- 「ラーメンを頻繁に食べたくなる人」は、数週間〜数ヶ月にわたって同じ料理を繰り返し検索する。プロセス内メモリ(`latest_suggestions.py`)では、サーバー再起動(Renderの休止など)で記憶が消えてしまい、長期的な「飽きさせない」目的には向かない。DBへの永続化が必要と判断した。

## 全体像

```
① 提案の多様性チェック(土台)
   ↓
② クイズ(栄養豆知識、1種類のみ)
   ↓ 週単位で集計
③ レーティング(did_replace成功率のみで計算。クイズは含めない)
```

---

## ① 提案の多様性チェック

### 新テーブル: `suggestion_history`
| 列 | 内容 |
|---|---|
| `id` | 連番主キー |
| `user_id` | ユーザーID |
| `dish_name` | 検索された元の料理名 |
| `ingredients` | 提案された材料(JSON) |
| `steps` | 提案された手順(JSON) |
| `embedding` | 提案全体(名前+材料+手順)のEmbeddingsベクトル(float配列。JSON列に保存し、`pgvector`は使わない) |
| `created_at` | 生成日時 |

`/suggest`が呼ばれるたび(検索するたび。`/record`で記録したかは問わない)、必ず1件保存する。記録しなかった提案も対象にするのが、上記「長期的に飽きさせない」という動機に対応するために重要な点。

`ingredients`・`steps`に加えて、`embedding`(提案全体をEmbeddings化したベクトル、float配列)も一緒に保存する。

### RAG的な検索(dish_nameの完全一致ではなく、意味的な近さで検索する)

当初`dish_name`の完全一致で履歴を絞り込む設計だったが、「ラーメン」「豚骨ラーメン」「つけ麺」のような表記ゆれをまたいで履歴を拾えない弱点があると判明したため、Embeddingsによる意味的な検索(RAGの考え方)に変更した。

ただし、`pgvector`(Supabaseのベクトル検索拡張)は不採用とした。理由: `pgvector`は数千〜数万件規模のベクトルを高速検索するための専用インデックス技術であり、今のデータ規模(1ユーザーあたり多くても数十件)では性能上のメリットが実質無く、クラスタリングのときと同様「技術的に凝っているが、今の規模には見合っていない」判断だったため。代わりに、その都度Pythonで全件取得し、その場でコサイン類似度を計算する方式を採用する(データが数千件規模に増えたら`pgvector`の導入を再検討する)。

```python
def search_similar(user_id: str, query_embedding: list[float], limit: int = 5) -> list[dict]:
    all_history = suggestion_history_repository.get_all(user_id)  # 全件取得(数十件程度)
    scored = [(item, cosine_similarity(query_embedding, item["embedding"])) for item in all_history]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, score in scored[:limit]]
```

### 処理の流れ
```python
# 1. 今回の料理名をベクトル化し、意味的に近い履歴を検索する(dish_nameの完全一致ではない)
query_embedding = get_embedding(dish_name)
recent = search_similar(user_id, query_embedding, limit=5)

# 2. 使われた食材をリスト化(重複除去)
avoid_ingredients = extract_main_ingredients(recent)  # 例: ["豆腐", "鶏肉"]

# 3. 提案を生成(avoid_ingredientsを渡す)
result = recipe_service.suggest_replacement(
    dish_name,
    target_daily_reduction_kcal=target,
    allergens=allergens,
    avoid_ingredients=avoid_ingredients,   # 新規引数
)

# 4. Embeddingsで類似度チェック(検索で見つかった最も近い1件と比較)
if recent:
    result_embedding = get_embedding(build_text(result))
    similarity = cosine_similarity(result_embedding, recent[0]["embedding"])
    if similarity > SIMILARITY_THRESHOLD:
        result = recipe_service.suggest_replacement(
            dish_name, target_daily_reduction_kcal=target,
            allergens=allergens, avoid_ingredients=avoid_ingredients,
        )  # 最大1回だけ再生成(コスト対策)
        result_embedding = get_embedding(build_text(result))

# 5. 履歴に保存(embeddingも一緒に保存する)
suggestion_history_repository.save(
    user_id, dish_name, result["ingredients"], result["steps"], result_embedding
)
```

`recipe_service.py`側の変更:
```python
def suggest_replacement(dish_name, target_daily_reduction_kcal=None, allergens=None, avoid_ingredients=None):
    ...
    avoid_instruction = ""
    if avoid_ingredients:
        avoid_instruction = f"\n過去に{'・'.join(avoid_ingredients)}を使っています。今回は避けてください。"
    ...
    messages=[{"role": "system", "content": SYSTEM_PROMPT + extra_instruction + allergen_instruction + avoid_instruction}, ...]
```

### 設定値(運用しながら調整する前提。いずれも実データでの検証は未実施)
```python
HISTORY_WINDOW = 5        # 直近何件分の食材を避けるか
SIMILARITY_THRESHOLD = 0.87  # これを超えたら再生成
MAX_RETRY = 1              # 再生成は最大1回まで(コスト対策)
```

**閾値0.87の根拠**: 実測で「同じ文章同士」=1.0、「ラーメンの提案1 vs 2(人間が見てちゃんと違うと判断)」=0.7684、「ラーメン vs ケーキ」=0.3714 という3点を確認した。0.7684は「合格ライン」なので、閾値はこれより上(かつ1.0に寄りすぎない)0.87程度を仮の初期値とした。サンプルが少ないため今後調整が必要。

### プロンプトの(a)〜(d)の軸について
`SYSTEM_PROMPT`内の「(a)食材変更 (b)調理法変更 (c)主食調整 (d)構成変更からランダムに選ぶ」という指示文はそのまま維持する。当初、AIに`axis_used`を自己申告させて外部から追跡・管理する案を検討したが、実際の提案は複数の軸に同時にまたがることが多く(例: 麺の種類とタンパク源を同時に変更)、正確な管理ができないと判断し不採用とした。具体的な食材名の重複チェックとEmbeddings類似度チェックが、軸管理が本来やろうとしていたことを代替してカバーする。

---

## ② クイズ(栄養豆知識のみ)

### 新テーブル: `quiz_results`
| 列 | 内容 |
|---|---|
| `id` | 連番主キー |
| `user_id` | ユーザーID |
| `question` | 出題内容 |
| `is_correct` | 正誤 |
| `created_at` | 回答日時 |

### 処理
①の提案生成と**同じAPI呼び出し**の中で、`SYSTEM_PROMPT`に一文追加し、JSON出力に3項目追加する(新しいAPI呼び出しは不要、コスト増なし)。

```json
{
  "...(既存の項目)...": "...",
  "trivia_question": "string",
  "trivia_choices": ["string", "string", "string"],
  "trivia_answer": "string"
}
```

判定は、ユーザーの選択と`trivia_answer`を比較するだけの単純な正解/不正解。**レーティングには一切影響しない、独立した機能**とする(検討の結果、置き換えの成否とクイズの正誤を混ぜないことにした)。

新ルート: `/quiz/answer`(POST)で正誤判定して`quiz_results`に保存。

---

## ③ レーティング(`did_replace`成功率のみで計算)

### 新テーブル: `user_ratings`
| 列 | 内容 |
|---|---|
| `user_id` | ユーザーID |
| `rating` | 現在のレーティング |
| `updated_at` | 最終更新日時 |

### 処理(週次バッチ)
```python
@app.route("/admin/update-ratings", methods=["POST"])
def update_ratings():
    for user_id in all_active_users():
        logs = filter_this_week(meal_logs_repository.fetch_logs(user_id))
        performance = success_rate(logs)  # did_replace=True の割合
        old_rating = user_ratings_repository.get(user_id) or 1200  # AtCoder初期値に倣う
        K = 32
        new_rating = old_rating + K * (performance * 100 - old_rating) / 100
        user_ratings_repository.update(user_id, new_rating)
    return jsonify({"status": "ok"})
```

色分け表示: 灰→茶→緑→水色→青→黄→橙→赤(AtCoderのレーティング色に倣う)

### 自動実行: GitHub Actions(無料)を採用
RenderのCron Jobsは実測で「月額最低$1」の費用がかかることが判明したため不採用。GitHub Actionsのスケジュール実行(無料枠内)で代替する。

```yaml
# .github/workflows/update-ratings.yml
name: Weekly Rating Update
on:
  schedule:
    - cron: "0 0 * * 1"  # 毎週月曜0時
jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - run: curl -X POST https://progate-hackathon-2026.onrender.com/admin/update-ratings
```

---

## 新規・変更ファイル一覧
| ファイル | 内容 |
|---|---|
| `suggestion_history_repository.py`(新規) | ①のCRUD |
| `quiz_results_repository.py`(新規) | ②のCRUD |
| `user_ratings_repository.py`(新規) | ③のCRUD |
| `recipe_service.py`(変更) | `avoid_ingredients`引数、トリビア出力を追加 |
| `app.py`(変更) | `/suggest`の拡張、`/quiz/answer`、`/admin/update-ratings`を追加 |
| `.github/workflows/update-ratings.yml`(新規) | 週次の自動トリガー |

## 実装順序(推奨)
1. ①(土台) ← **実装・動作確認済み**。実際に「鶏ささみ・白米」中心の提案→次回は避けて「カリフラワー・鶏むね肉」中心に切り替わることを確認済み
2. ②(クイズ)は①に相乗りする形で追加(コスト増なしなので、次に着手しやすい) ← 未実装
3. ③(レーティング)は、①②の運用でデータが溜まってから、一番最後に着手する ← 未実装

## 成功指標
| 指標 | 内容 | 測定タイミング |
|---|---|---|
| 直近5件内のユニーク食材数 | ①が数字上、多様化に効いているか | 導入直後から |
| 提案同士の平均類似度 | ①の数字上の変化 | 導入直後から |
| クイズ正答率 | ②の定着度 | 導入直後から |
| `did_replace`の成功率の推移 | 全体として実際に行動が変わったか(最重要) | 数週間の運用後 |

## 正直な限界・未検証事項
- `HISTORY_WINDOW`・`SIMILARITY_THRESHOLD`・レーティング計算式のK値は、いずれも実データでの検証がまだ行われていない仮の初期値
- Embeddings類似度チェックが実際に提案の質を改善するかは未検証(「動くこと」と「価値があること」は別、という前提で臨む)
- `suggestion_history`・`quiz_results`・`user_ratings`は、いずれも新規のSupabaseテーブル作成が必要(本番の`meal_logs`とは別の、新設テーブル)
- チームとしてこの機能を採用するかどうかは未決定。あくまで個人のプロトタイプ・ポートフォリオとしての設計

## 参考: 発想の経緯
- 「継続予測」「体重推移予測(機能5)」「Embeddings+クラスタリング」など、複数の機械学習機能案を検討したが、いずれもデータ不足(コールドスタート問題)にぶつかり不採用とした
- アイデア出しの手法として「課題から考える」「関係ないワードから考える」「使いたい技術から考える」の3ルートを使い、「関係ないワードから考える」ルートで「競技プログラミング(AtCoderのレーティング・diff)」「海亀のスープ(謎解き形式)」との掛け合わせを試した結果、レーティング制とクイズ形式に着地した
