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
import radio_memory_repository
import radio_prompt
import voicevox_client
import weight_repository

KCAL_MILESTONE_THRESHOLDS = [1000, 5000, 10000, 20000, 50000]

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


def _calculate_streak(user_id: str) -> int:
    """直近のログから、最新を起点に連続で置き換え(did_replace=True)している件数を数える。"""
    logs = meal_logs_repository.fetch_logs(user_id, limit=30)
    streak = 0
    for log in logs:
        if not log["did_replace"]:
            break
        streak += 1
    return streak


def _ask_dj_reaction(fact_description: str) -> str:
    """自己ベスト更新などの事実に対する、DJの一言の反応をAIに書かせる(1回だけ)。"""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "あなたは深夜ラジオのDJ二人組です。以下の出来事に対する、DJとしての"
                "一言の反応を1文で書いてください。説明文や前置きは不要、反応の文章だけ返してください。",
            },
            {"role": "user", "content": fact_description},
        ],
    )
    return response.choices[0].message.content.strip()


def _save_milestone(user_id: str, fact_description: str) -> None:
    reaction = _ask_dj_reaction(fact_description)
    radio_memory_repository.save_memory(
        user_id, content=f"{fact_description}。{reaction}", importance=8, kind="milestone"
    )


def _check_and_save_milestones(user_id: str, profile: dict) -> None:
    """実データと過去の自己ベストを比較し、更新していればmilestoneとして記録する。

    自己ベストの値自体はuser_metadataに持たせる(favorite_thingsなどと同じ場所)。
    判定はすべてコード側の数値比較で行い、AIには判定させない(設計書6-4章)。
    """
    updates: dict = {}

    streak = _calculate_streak(user_id)
    best_streak = profile.get("best_streak", 0)
    if streak >= 2 and streak > best_streak:
        _save_milestone(user_id, f"連勝記録を更新した(今までの最高{best_streak}日→今回{streak}日)")
        updates["best_streak"] = streak

    latest_weight = weight_repository.get_latest_weight(user_id)
    best_weight = profile.get("best_weight")
    if latest_weight is not None and (best_weight is None or latest_weight < best_weight):
        if best_weight is not None:  # 初回の記録はお祝いせず、基準値として覚えるだけにする
            _save_milestone(user_id, f"体重の自己ベストを更新した({best_weight}kg→{latest_weight}kg)")
        updates["best_weight"] = latest_weight

    total_saved = meal_logs_repository.fetch_total_saved(user_id)
    reached_level = profile.get("kcal_milestone_level", 0)
    for i, threshold in enumerate(KCAL_MILESTONE_THRESHOLDS):
        if total_saved >= threshold and reached_level < i + 1:
            _save_milestone(user_id, f"累計削減カロリーが{threshold}kcalを突破した")
            reached_level = i + 1
    if reached_level != profile.get("kcal_milestone_level", 0):
        updates["kcal_milestone_level"] = reached_level

    goal = goal_repository.fetch_latest_goal(user_id)
    if goal and latest_weight is not None and latest_weight <= float(goal["target_weight_kg"]):
        if profile.get("goal_achieved_id") != goal["id"]:
            _save_milestone(user_id, f"目標体重{goal['target_weight_kg']}kgを達成した")
            updates["goal_achieved_id"] = goal["id"]

    if updates:
        auth_service.update_profile(user_id, **updates)


def _maybe_generate_reflection(user_id: str, episode_count: int) -> None:
    """生成回数が10の倍数のときだけ、直近の記憶をもとに「最近の傾向」を1件だけ追加する。"""
    if episode_count % 10 != 0:
        return

    memories = radio_memory_repository.fetch_recent_memories(user_id, limit=15)
    if not memories:
        return

    memories_text = "\n".join(f"- {m['content']}" for m in memories)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "以下は、ある人の話をしてきた深夜ラジオのDJたちの、これまでの記憶の一覧です。"
                "これらを踏まえて、「最近の傾向」を1〜2文で振り返ってください。"
                "説明文や前置きは不要、振り返りの文章だけ返してください。",
            },
            {"role": "user", "content": memories_text},
        ],
    )
    reflection = response.choices[0].message.content.strip()
    radio_memory_repository.save_memory(user_id, content=reflection, importance=9, kind="reflection")


MAX_EPISODES_PER_DAY = 5

# 「好きなこと」「興味があること」は毎回プロンプトに渡すと、AIにとって一番使いやすい
# 話題になってしまい、結果的に同じ話ばかりになる。そのため、コード側で頻度そのものを
# 制限する(AIに「自然な時だけ使って」と指示するだけでは抑えきれなかったため)。
# 「一度使ったら二度と使わない」にすると、今度はせっかく書いた入力が二度と日の目を
# 見なくなってしまうので、そうはせず、間隔を空けてたまに登場する形にする。
FAVORITE_THINGS_INTERVAL = 20
INTERESTS_INTERVAL = 20


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
    profile = auth_service.get_profile(user_id)
    _check_and_save_milestones(user_id, profile)

    events_text = _build_events_text(user_id)
    episode_number = profile.get("radio_episode_count", 0) + 1
    favorite_things = (
        profile.get("favorite_things", "") if episode_number % FAVORITE_THINGS_INTERVAL == 0 else ""
    )
    # 「好きなこと」と同じ回に重ならないよう、半周期ずらして登場させる
    # (2つとも間引きつつ、出てくる時は毎回違う話題になるようにするため)。
    interests = (
        profile.get("interests", "")
        if episode_number % INTERESTS_INTERVAL == INTERESTS_INTERVAL // 2
        else ""
    )
    recent_scripts = radio_episode_repository.fetch_recent_scripts(user_id, limit=2)
    memories = radio_memory_repository.fetch_top_memories(user_id, limit=3)
    diary_note = profile.get("pending_diary_note", "")

    user_prompt = radio_prompt.build_user_prompt(
        events_text, favorite_things, recent_scripts, memories, diary_note, interests
    )

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

    if script.get("highlight"):
        radio_memory_repository.save_memory(user_id, content=script["highlight"], importance=6, kind="highlight")

    speaker_a = profile.get("voice_a_id", voicevox_client.DEFAULT_SPEAKER_A)
    speaker_b = profile.get("voice_b_id", voicevox_client.DEFAULT_SPEAKER_B)
    audio_bytes = voicevox_client.synthesize_script(script["lines"], speaker_a, speaker_b)

    script_text = "\n".join(f"{line['speaker']}: {line['text']}" for line in script["lines"])
    episode = radio_episode_repository.generate_and_store_episode(
        user_id=user_id,
        script=script_text,
        audio_bytes=audio_bytes,
    )

    updates = {"radio_episode_count": episode_number}
    if diary_note:
        updates["pending_diary_note"] = ""  # 使ったら「今日の分」として空にリセットする
    auth_service.update_profile(user_id, **updates)
    _maybe_generate_reflection(user_id, episode_number)

    return episode
