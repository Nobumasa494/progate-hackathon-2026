"""VOICEVOXエンジン(ローカルで起動しているもの)を使って、台本を音声にする。

前提: VOICEVOXエンジンが http://localhost:50021 で起動していること。
"""

from __future__ import annotations

import io
import os
import wave
from concurrent.futures import ThreadPoolExecutor

import httpx

DEFAULT_SPEAKER_A = 3  # ずんだもん(ノーマル)
DEFAULT_SPEAKER_B = 2  # 四国めたん(ノーマル)

# ローカル開発時は起動している自分のVOICEVOXエンジンを使う。
# Renderなど本番環境では、VOICEVOXエンジンを別サービスとして立て、
# 環境変数VOICEVOX_URLにそのサービスのURLを設定する(設計書5-1・5-4章参照)。
VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://localhost:50021")


def list_speakers() -> list[dict]:
    """VOICEVOXエンジンに、今使えるキャラクター(話者)の一覧を問い合わせる。

    戻り値の例:
        [{"name": "四国めたん", "styles": [{"id": 2, "name": "ノーマル"}, ...]}, ...]
    """
    response = httpx.get(f"{VOICEVOX_URL}/speakers", timeout=10)
    speakers = response.json()
    return [
        {
            "name": speaker["name"],
            "styles": [{"id": style["id"], "name": style["name"]} for style in speaker["styles"]],
        }
        for speaker in speakers
    ]


def synthesize_line(text: str, speaker: int) -> bytes:
    """1セリフ分の音声(wavバイト列)を作る。"""
    query = httpx.post(
        f"{VOICEVOX_URL}/audio_query",
        params={"text": text, "speaker": speaker},
        timeout=60,
    ).json()
    audio = httpx.post(
        f"{VOICEVOX_URL}/synthesis",
        params={"speaker": speaker},
        json=query,
        timeout=60,
    )
    return audio.content


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
    """
    def _synthesize(line: dict) -> bytes:
        speaker_id = speaker_a if line["speaker"] == "A" else speaker_b
        return synthesize_line(line["text"], speaker_id)

    with ThreadPoolExecutor(max_workers=8) as executor:
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
