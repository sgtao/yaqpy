"""「AI に相談」画面の、プロンプトへの反映のロジック（Flet 非依存。v0.7.0）。

左の欄（利用者の入力：データ例・やりたい変換）を、右の欄（AI への相談文）へ**ボタンを押したときだけ**
一方向に差し込む。右の欄は全文を編集できるので、リアルタイムの双方向の同期はしない
（どちらが正か曖昧になるため）。
"""

from __future__ import annotations

from yaqpy.app.selfdoc import GUIDE_PROMPT_PLACEHOLDER


def apply_user_input(prompt: str, user_text: str) -> str:
    """相談文に、利用者の入力を反映する。

    * 案内の一文（``GUIDE_PROMPT_PLACEHOLDER``）が残っていれば、それを入力で置き換える
    * 無ければ（2 回目以降・編集済み）、相談文の末尾に空行を挟んで追記する

    入力が空（空白だけ）なら何もしない。
    """
    text = user_text.strip("\n")
    if not text.strip():
        return prompt
    if GUIDE_PROMPT_PLACEHOLDER in prompt:
        return prompt.replace(GUIDE_PROMPT_PLACEHOLDER, text, 1)
    return f"{prompt.rstrip()}\n\n{text}\n"
