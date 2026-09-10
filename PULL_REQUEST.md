## 変更の概要
機能3（目標管理）のバックエンドを新規実装した。Supabaseのgoalsテーブルから体重目標を取得・追加し、1日当たりの目標削減カロリーを自動計算するAPIを構築しました。

## 変更内容
- 体重目標の取得・新規作成・カロリー計算が可能なエンドポイントを追加
- Supabaseへの接続とCRUD処理を実装
- 7200kcal/1kgの計算式に基づく日次目標削減カロリーの算出ロジックを追加
- ローカル検証用のサンプルデータを用意

## 動作確認
- コマンドラインでJSON入力から計算結果（2400.0 kcal）を確認
- FastAPIサーバーを起動し、Swagger UIで3つのエンドポイントを検証

## 📚 このPRに含まれている概念
- FastAPIのエンドポイント定義 — `main.py`
- Supabaseクライアント接続 — `goal_repository.py`
- CRUD（目標の作成・取得） — `goal_repository.py`
- カロリー計算ロジック（7200kcal/1kg） — `target_calculation.py`
- ダミーデータと本物の差し替え設計 — `main.py`, `goal_repository.py`
