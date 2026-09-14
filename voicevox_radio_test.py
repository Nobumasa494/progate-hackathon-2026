"""台本生成プロンプト(radio_prompt.py)の動作確認用スクリプト。

固定のテストデータで台本を生成し、VOICEVOXで音声化してradio_test.wavに書き出す。
実際のユーザーデータを使う本番相当の処理は radio_service.py を参照。
"""

import json
import os

from openai import OpenAI
from dotenv import load_dotenv

import radio_prompt
import voicevox_client

load_dotenv()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

USER_PROMPT = """
今日の出来事:
- かつ丼を我慢して、豆腐ハンバーグ定食を選んだ(450kcal、900kcalから削減)
- 3日連続で置き換えに成功している
- 体重は先週より1.2kg減った
- 目標まであと1.2kg

今日食べたものの参考情報(雑学ジャンルでgを選んだ場合の材料。他のジャンルを選んでもよい):
- 主な食材: 豆腐、しらたき(こんにゃく芋が原料)

本人の好きなこと:
- 映画鑑賞(最近は考察系のミステリーにハマっている)

前回までの話:
- 前回、パスタをから揚げ定食に変えるか最後まで悩んで結局から揚げにした、という話をしていた
- 「次こそは我慢できるかな」という話で終わっていた
"""

response = client.chat.completions.create(
    model="gpt-4o-mini",
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": radio_prompt.SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ],
)
script = json.loads(response.choices[0].message.content)
print(json.dumps(script, ensure_ascii=False, indent=2))

print("音声を生成中...")
audio_bytes = voicevox_client.synthesize_script(script["lines"])

with open("radio_test.wav", "wb") as f:
    f.write(audio_bytes)

print("radio_test.wav を作成しました")
