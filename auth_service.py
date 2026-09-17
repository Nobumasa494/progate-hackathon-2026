"""機能: ユーザー認証(サインアップ・ログイン)

Supabase Auth(メール/パスワード)を、サーバー側(Flaskのセッション)から使う。
ブラウザにはSupabaseの鍵を一切渡さず、すべてFlask経由で行う。
"""

from __future__ import annotations

import os

from supabase import create_client

from goal_repository import get_client


def _fresh_client():
    """sign_up/sign_in専用の、使い捨てのSupabaseクライアントを作る。

    client.auth.sign_up()/sign_in_with_password()は、そのクライアントの内部状態に
    「今ログイン中のユーザー」の認証情報を書き込む。goal_repository.get_client()が
    返す共有クライアント(複数箇所・複数リクエストで使い回されるもの)でこれを行うと、
    誰かがログインした瞬間、共有クライアントの以降の全操作がそのユーザーの権限で
    実行されてしまう(複数人が同時に使うと、他人の操作に影響しうる深刻な問題になる)。
    そのためここだけは、使い終わったら捨てる専用のクライアントを使う。
    """
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def sign_up(email: str, password: str, favorite_things: str = ""):
    """新規登録する。成功したらユーザー情報(id・emailなど)を返す。

    favorite_thingsは深夜ラジオ機能(実験中)で使う「好きなこと」のメモ。
    user_metadataとして保存され、後からuser.user_metadata["favorite_things"]で読める。
    """
    client = _fresh_client()
    result = client.auth.sign_up({
        "email": email,
        "password": password,
        "options": {"data": {"favorite_things": favorite_things}},
    })
    return result.user


def sign_in(email: str, password: str):
    """ログインする。成功したらユーザー情報を返す。

    メールアドレス・パスワードが違う場合は例外(AuthApiError)が飛ぶので、
    呼び出し側でtry/exceptして扱う。
    """
    client = _fresh_client()
    result = client.auth.sign_in_with_password({"email": email, "password": password})
    return result.user


def get_profile(user_id: str) -> dict:
    """user_metadataをそのまま返す(favorite_things・voice_a_id・voice_b_idなどをまとめて持つ)。

    admin APIを使うので、SUPABASE_KEYはsecret keyである必要がある(既存の設定を流用)。
    """
    client = get_client()
    user = client.auth.admin.get_user_by_id(user_id).user
    return user.user_metadata or {}


def update_profile(user_id: str, **fields) -> None:
    """user_metadataの一部だけを更新する(他のキーは消さずに残す)。

    Supabaseのadmin APIはuser_metadataを丸ごと置き換える仕様のため、
    ここで「今の値を読む → 渡された分だけ上書き → 書き戻す」というマージ処理をしている。
    """
    client = get_client()
    current = get_profile(user_id)
    current.update(fields)
    client.auth.admin.update_user_by_id(user_id, {"user_metadata": current})


def get_favorite_things(user_id: str) -> str:
    """好きなことを取得する(未登録なら空文字)。"""
    return get_profile(user_id).get("favorite_things", "")


def update_favorite_things(user_id: str, favorite_things: str) -> None:
    """好きなことを後から更新する(サインアップ済みユーザー向け)。"""
    update_profile(user_id, favorite_things=favorite_things)


def update_pending_diary_note(user_id: str, note: str) -> None:
    """「今日、DJたちに教えたいことある?」への回答を保存する(食事ログ記録時に一緒に入力される)。

    「今日の分」として次のラジオ生成時に一度だけ使われ、使ったら空にリセットされる
    (radio_service.py参照)。
    """
    update_profile(user_id, pending_diary_note=note)


def get_allergens(user_id: str) -> list[str]:
    """アレルゲン(特定原材料)の一覧を取得する(未設定なら空リスト)。

    例: ["えび", "小麦", "乳"]
    """
    value = get_profile(user_id).get("allergens", [])
    if isinstance(value, str):
        value = [a.strip() for a in value.split(",") if a.strip()]
    return [a for a in value if isinstance(a, str)]


def update_allergens(user_id: str, allergens: list[str]) -> None:
    """アレルゲン(特定原材料)の一覧を保存する(空リスト=未設定)。"""
    update_profile(user_id, allergens=allergens)
