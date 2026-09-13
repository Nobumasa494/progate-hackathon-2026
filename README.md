# 置き換えダイエットアプリ(Progateハッカソン)

食べたい料理名を入力すると、AIがカロリーを抑えた置き換えレシピを提案するアプリです。
実際に食べた内容・体重・目標を記録し、目標に応じて提案の内容も自動で調整されます。

## 機能

| 画面 | URL | できること |
|---|---|---|
| レシピ提案 | `/` | 料理名を入力し、AIに置き換えレシピを提案してもらう |
| 食事ログ | `/record` | 提案をもとに、実際に食べた内容・カロリーを記録する |
| 目標 | `/goals` | 目標体重・期日を設定し、必要な削減カロリーと進捗を見る |
| 体重記録 | `/weight-log` | 体重を記録し、推移をグラフで見る |
| ログイン / 新規登録 | `/login` `/signup` | アカウントごとにデータを管理する |

## 使用技術

- **Flask** — Webアプリのフレームワーク(画面・APIともにこれ1つで配信)
- **Supabase** — データベース(体重・目標・食事ログ)と認証(Supabase Auth)
- **OpenAI API** — 置き換えレシピの提案(`gpt-4o-mini`)

## 機能同士の連携

4つの機能はそれぞれ独立させず、以下のように連携しています。

- **レシピ提案 → 食事ログ**: 提案結果を`latest_suggestions.py`に一時保存し、記録画面が取得して使う
- **体重記録 → 目標**: 目標の計算に使う「現在の体重」は、体重記録の最新値を自動で使う(手入力しない)
- **目標 → レシピ提案**: 目標の削減ペースをAIへの指示に反映する。ただし安全のため、AIに伝える削減量には上限(`MAX_SAFE_DAILY_REDUCTION_KCAL`)を設けている

詳しい設計の経緯は、開発中にまとめた設計メモを参照(社内共有のみ)。

## セットアップ

### 1. 必要なもの

- Python 3.12以上
- Supabaseプロジェクト(`goals`・`meal_logs`・`weight_logs`テーブルを作成済みのもの)
- OpenAI APIキー

### 2. 環境変数を設定する

`.env.example` をコピーして `.env` を作成し、値を埋めてください。

```bash
cp .env.example .env
```

| 変数名 | 内容 |
|---|---|
| `OPENAI_API_KEY` | OpenAIのAPIキー |
| `SUPABASE_URL` | SupabaseプロジェクトのURL |
| `SUPABASE_KEY` | Supabaseのsecret key(サーバー側専用。ブラウザには渡さない) |
| `FLASK_SECRET_KEY` | ログインセッション用の秘密鍵。`python -c "import secrets; print(secrets.token_hex(32))"` で生成する |

### 3. 依存パッケージをインストール

```bash
python -m venv venv
source venv/bin/activate   # Windowsは venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 起動する

```bash
python app.py
```

`http://127.0.0.1:8000` で起動します。

## 本番向けの起動(参考)

開発用サーバー(`python app.py`)ではなく、`gunicorn`を使う。

```bash
gunicorn app:app
```

## 補足: 開発用の道具

- `example_get_goal.py` — `goal_repository.py`をコマンドラインから単体で試す(`python example_get_goal.py <user_id>`)
- `sample_latest_goal.json` — `target_calculation.py`を単体で試すためのサンプルデータ(`python target_calculation.py sample_latest_goal.json`)
