"""深夜ラジオ機能(実験中)のメイン処理。

「実データを集める → 台本を作る(OpenAI) → 音声にする(VOICEVOX) → 保存する(Storage/DB)」
までを1つの関数にまとめたもの。

前提:
    - VOICEVOXエンジンがローカルで起動していること(voicevox_client.py参照)
    - OPENAI_API_KEY が環境変数に設定されていること
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from openai import OpenAI

import auth_service
import goal_repository
import meal_logs_repository
import radio_episode_repository
import radio_prompt
import voicevox_client

# 「今、裏で生成中のuser_id」を覚えておくだけの、プロセス内メモリ(latest_suggestions.pyと同じ考え方)。
# サーバーを再起動すると消えるが、生成中かどうかの一時的な表示用なので問題ない。
_generating_user_ids: set[str] = set()


def is_generating(user_id: str) -> bool:
    """今、このユーザーの分を裏で生成中かどうか。"""
    return user_id in _generating_user_ids


def _build_events_text(user_id: str) -> str:
    """meal_logs・goalsの実データから「今日の出来事」の説明文を組み立てる。"""
    lines = []

    logs = meal_logs_repository.fetch_logs(user_id, limit=1)
    if logs:
        log = logs[0]
        if log["did_replace"]:
            lines.append(
                f"- {log['dish_name']}を我慢して、{log['suggested_replacement_name']}を選んだ"
                f"({log['actual_calories']}kcal、{log['original_calories']}kcalから削減)"
            )
        else:
            lines.append(f"- {log['dish_name']}を我慢できず、そのまま食べた")

    goal = goal_repository.get_latest_goal_with_daily_reduction(user_id)
    if goal and not goal.get("expired"):
        saved = meal_logs_repository.fetch_total_saved(user_id, goal_id=goal.get("id"))
        lines.append(f"- 目標まであと{goal['target_weight_kg']}kgに向けて、これまでに{saved}kcal分の削減に成功している")

    if not lines:
        lines.append("- 特に大きな出来事はない、いつも通りの1日だった")

    return "\n".join(lines)


MAX_EPISODES_PER_DAY = 5


def _today_start_iso() -> str:
    """今日の0時(UTC)をISO8601文字列で返す。"""
    today = datetime.now(timezone.utc).date()
    return datetime(today.year, today.month, today.day, tzinfo=timezone.utc).isoformat()


def has_episode_today(user_id: str) -> bool:
    """今日すでに1件以上エピソードを生成済みかどうか。"""
    return radio_episode_repository.count_episodes_since(user_id, _today_start_iso()) > 0


def reached_daily_limit(user_id: str) -> bool:
    """今日、生成できる上限(1日MAX_EPISODES_PER_DAY回)に達しているかどうか。"""
    return radio_episode_repository.count_episodes_since(user_id, _today_start_iso()) >= MAX_EPISODES_PER_DAY


def maybe_generate_in_background(user_id: str) -> None:
    """今日まだ生成していなければ、裏側で(別スレッドで)生成を開始する。

    事前生成の仕組み(設計書8章): 食事ログ記録をきっかけに、
    ユーザーを待たせずに裏で生成しておき、次にアプリを開いたときには出来上がっている状態にする。
    1日にMAX_EPISODES_PER_DAY回までは自動生成する(それ以上は手動ボタンでのみ生成可能)。
    リクエストへのレスポンスは待たずに返す(生成の成否はここでは気にしない)。
    """
    if reached_daily_limit(user_id) or is_generating(user_id):
        return

    def _run():
        try:
            generate_todays_episode(user_id)
        except Exception as e:
            # バックグラウンド処理なので、失敗してもリクエストには影響させない。
            # ログにだけ残す(本番ではロガーに置き換える)。
            print(f"[radio] 生成に失敗しました user_id={user_id}: {e}")

    threading.Thread(target=_run, daemon=True).start()


def generate_todays_episode(user_id: str) -> dict:
    """そのユーザーの今日のエピソードを作り、保存する。戻り値はradio_episodesの行。

    is_generatingの印を、処理の間だけ立てておく(手動ボタン・自動生成どちらの経路でも
    ここを通るので、/radio/status で一律に生成中かどうか確認できる)。
    """
    _generating_user_ids.add(user_id)
    try:
        return _generate_todays_episode(user_id)
    finally:
        _generating_user_ids.discard(user_id)


def _generate_todays_episode(user_id: str) -> dict:
    events_text = _build_events_text(user_id)
    favorite_things = auth_service.get_favorite_things(user_id)
    recent_scripts = radio_episode_repository.fetch_recent_scripts(user_id, limit=2)

    user_prompt = radio_prompt.build_user_prompt(events_text, favorite_things, recent_scripts)

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": radio_prompt.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    script = json.loads(response.choices[0].message.content)

    profile = auth_service.get_profile(user_id)
    speaker_a = profile.get("voice_a_id", voicevox_client.DEFAULT_SPEAKER_A)
    speaker_b = profile.get("voice_b_id", voicevox_client.DEFAULT_SPEAKER_B)
    audio_bytes = voicevox_client.synthesize_script(script["lines"], speaker_a, speaker_b)

    script_text = "\n".join(f"{line['speaker']}: {line['text']}" for line in script["lines"])
    return radio_episode_repository.generate_and_store_episode(
        user_id=user_id,
        script=script_text,
        audio_bytes=audio_bytes,
    )
