"""機能1→機能2の連携: 「そのユーザーの最新の提案」を一時的に保持する。

Shared Databaseパターンの簡易版。本番ではSupabaseの専用テーブルに置き換える想定だが、
今はローカル検証用にメモリ上の辞書に保存する（DUMMY_GOALS / DUMMY_LOGS と同じ方針）。

/suggest が呼ばれるたびに、そのユーザーのぶんを上書きする。
記録画面（機能2）は、ブラウザに何も保持させず、ここへ都度取りに来る。
"""

from __future__ import annotations

from typing import Optional

_LATEST_SUGGESTIONS: dict[str, dict] = {}


def save_latest_suggestion(user_id: str, suggestion: dict) -> None:
    _LATEST_SUGGESTIONS[user_id] = suggestion


def get_latest_suggestion(user_id: str) -> Optional[dict]:
    return _LATEST_SUGGESTIONS.get(user_id)
