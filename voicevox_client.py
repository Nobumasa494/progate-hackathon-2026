"""VOICEVOXエンジン(ローカルで起動しているもの)を使って、台本を音声にする。

前提: VOICEVOXエンジンが http://localhost:50021 で起動していること。
"""

from __future__ import annotations

import io
import os
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import httpx

DEFAULT_SPEAKER_A = 3  # ずんだもん(ノーマル)
DEFAULT_SPEAKER_B = 2  # 四国めたん(ノーマル)

# ローカル開発時は起動している自分のVOICEVOXエンジンを使う。
# Renderなど本番環境では、VOICEVOXエンジンを別サービスとして立て、
# 環境変数VOICEVOX_URLにそのサービスのURLを設定する(設計書5-1・5-4章参照)。
VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://localhost:50021")


def wake_up(timeout: int = 10, retries: int = 15, interval: int = 5) -> None:
    """VOICEVOXが休止状態から完全に起きるまで待つ、軽いリクエスト。

    本番ではVOICEVOXが別サービス(無料枠)で動いており、休止状態からの起動待ちだけで
    50秒以上かかることがある(Renderの無料インスタンスの仕様)。これを呼ばずにいきなり
    音声合成を並列で送りつけると、起きかけの不安定な状態に負荷が集中してしまうため、
    先にこの軽いリクエストで完全に起きるのを待ってから、本番の合成を始める。

    起動途中は、応答自体は返ってくるが中身が502(Bad Gateway)ということがある
    (コンテナがまだポートを開ける前の状態)。ここでraise_for_status()を確認せずに
    「応答が来た=起きた」と判定すると、まだ起動中なのに合成処理に進んでしまい、
    そちらも502で失敗する。そのため200が返るまで、一定間隔でリトライする。

    デフォルトは、リクエストを受けたFlaskのスレッドを直接ブロックしない裏スレッドから
    呼ばれること(synthesize_script()や、radio_service.get_voices_status()経由の
    list_speakers())を前提に、余裕を持たせた値にしている(最悪ケースで15×10+14×5=220秒。
    Renderの「50秒以上」という説明には上限が書かれていないため、多少余裕を持たせておきたい)。

    もしリクエストを受けたFlaskのスレッドの中で直接(裏スレッドを介さず)同期的に
    呼ぶ場合は、待ちすぎるとそのスレッドを長時間塞いでしまうため、呼び出し側で
    timeout/retriesを短く指定すること。
    """
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = httpx.get(f"{VOICEVOX_URL}/version", timeout=timeout)
            response.raise_for_status()
            return
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(interval)
    raise last_error


def list_speakers() -> list[dict]:
    """VOICEVOXエンジンに、今使えるキャラクター(話者)の一覧を問い合わせる。

    戻り値の例:
        [{"name": "四国めたん", "styles": [{"id": 2, "name": "ノーマル"}, ...]}, ...]

    先にwake_up()でVOICEVOXが完全に起きているのを確認してから問い合わせる
    (起動途中は応答が502になり、それをそのまま.json()すると分かりにくいエラーになるため)。

    呼び出し元のradio_service.get_voices_status()は裏スレッドからこの関数を呼ぶ
    (リクエストを受けたFlaskのスレッドを直接ブロックしない)ため、wake_up()は
    デフォルトの余裕がある値(最悪約220秒)をそのまま使う。実際の本番ログで、
    完全に休止した状態からの起動に90秒以上かかる例が確認されているため、
    短く切り上げて失敗させるより、しっかり待てる方を優先する。
    """
    wake_up()
    response = httpx.get(f"{VOICEVOX_URL}/speakers", timeout=90)
    response.raise_for_status()
    speakers = response.json()
    return [
        {
            "name": speaker["name"],
            "styles": [{"id": style["id"], "name": style["name"]} for style in speaker["styles"]],
        }
        for speaker in speakers
    ]


def synthesize_line(text: str, speaker: int, retries: int = 4) -> bytes:
    """1セリフ分の音声(wavバイト列)を作る。

    タイムアウトは長めの120秒にしている。本番ではVOICEVOXが別サービス(無料枠)で
    動いており、休止状態からの起動待ちだけで50秒以上かかることがあるため
    (Renderの無料インスタンスの仕様)、60秒程度だと起動待ち+実際の合成時間で
    タイムアウトしてしまう実例があった。

    起きた直後など、一時的に不安定な応答(空の応答や502)を返すことがあったため、
    失敗したら少し待ってから自動で再試行する(最大retries回)。raise_for_status()で
    エラー時にステータスコード付きの分かりやすい例外にしている(空の応答を
    そのままJSONとして読もうとして分かりにくいエラーになるのを防ぐため)。

    retriesは、以前2回(最大約9秒粘る)にしていたが、実際の本番で
    「synthesize_script側のwake_up()は/versionに成功しているのに、直後の
    /audio_queryだけがまだ502になる」という例が確認された。VOICEVOXが完全に
    安定するまでには/versionが通ってからも少し時間がかかることがあるとみられるため、
    4回(最大約20秒)に増やした。もっと粘る(6回・約30秒)ことも検討したが、
    VOICEVOXが一時的な不調ではなく完全にダウンしている場合、粘る時間が長いほど
    生成失敗までの時間も伸び、その間裏スレッドがメモリを使い続けてしまう
    (無料枠は512MBしかなく、メモリ超過による再起動が実際に繰り返し起きているため)。
    502の再発防止と、ダウン時の被害を広げすぎないことのバランスを取った値。
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            query_response = httpx.post(
                f"{VOICEVOX_URL}/audio_query",
                params={"text": text, "speaker": speaker},
                timeout=120,
            )
            query_response.raise_for_status()
            audio = httpx.post(
                f"{VOICEVOX_URL}/synthesis",
                params={"speaker": speaker},
                json=query_response.json(),
                timeout=120,
            )
            audio.raise_for_status()
            return audio.content
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(5)
    raise last_error


def synthesize_script(
    lines: list[dict],
    speaker_a: int = DEFAULT_SPEAKER_A,
    speaker_b: int = DEFAULT_SPEAKER_B,
) -> bytes:
    """台本(speaker/textのリスト)を、話者ごとに音声化して1本のwavに結合する。

    lines: [{"speaker": "A", "text": "..."}, ...]
    speaker_a / speaker_b: DJ A・DJ Bに使うVOICEVOXの話者ID(ユーザーが選べる、6-4章参照)
    戻り値: 結合済みのwavファイルのバイト列(メモリ上のみ。ディスクには書かない)

    セリフごとの合成は並列で行う。VOICEVOXはローカルのHTTPサーバーで、1セリフごとに
    2回の通信(audio_query→synthesis)が発生するため、40〜60セリフを順番にやると
    生成時間の大半をここが占めてしまう。ThreadPoolExecutor.map()は入力順を保ったまま
    結果を返すので、並列化してもセリフの再生順は崩れない。

    並列化する前に、まずwake_up()で1回だけ軽いリクエストを送り、VOICEVOXが
    完全に起きているのを確認してから始める(起きかけの状態に負荷をかけないため)。

    並列数は2に抑えている。本番のVOICEVOX(無料インスタンス)はCPUが0.1しか
    割り当てられておらず、並列数を増やしても使えるCPUの合計は変わらないため、
    多く並列化するとその小さいCPU枠を奪い合って1つ1つの処理が遅くなり、
    タイムアウトしやすくなる。
    """
    wake_up()

    def _synthesize(line: dict) -> bytes:
        speaker_id = speaker_a if line["speaker"] == "A" else speaker_b
        return synthesize_line(line["text"], speaker_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        line_audio = list(executor.map(_synthesize, lines))

    output_buffer = io.BytesIO()
    output_wave = wave.open(output_buffer, "wb")
    for i, audio_bytes in enumerate(line_audio):
        line_wave = wave.open(io.BytesIO(audio_bytes), "rb")
        if i == 0:
            output_wave.setparams(line_wave.getparams())
        output_wave.writeframes(line_wave.readframes(line_wave.getnframes()))
        line_wave.close()
    output_wave.close()

    return output_buffer.getvalue()
