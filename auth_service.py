"""機能: ユーザー認証(サインアップ・ログイン)

Supabase Auth(メール/パスワード)を、サーバー側(Flaskのセッション)から使う。
ブラウザにはSupabaseの鍵を一切渡さず、すべてFlask経由で行う。
"""

from __future__ import annotations

from goal_repository import get_client


def sign_up(email: str, password: str):
    """新規登録する。成功したらユーザー情報(id・emailなど)を返す。"""
    client = get_client()
    result = client.auth.sign_up({"email": email, "password": password})
    return result.user


def sign_in(email: str, password: str):
    """ログインする。成功したらユーザー情報を返す。

    メールアドレス・パスワードが違う場合は例外(AuthApiError)が飛ぶので、
    呼び出し側でtry/exceptして扱う。
    """
    client = get_client()
    result = client.auth.sign_in_with_password({"email": email, "password": password})
    return result.user
