"""tts/language.py — 文字語言判斷：CJK 偵測、espeak 語音選擇、中英分段。"""


def _has_cjk(text: str) -> bool:
    """文字中是否含 CJK 漢字（用於 espeak 語言切換）。"""
    return any("一" <= ch <= "鿿" for ch in text)


def _pick_espeak_voice(text: str) -> str:
    """依文字內容選 espeak 語音：含漢字→普通話(cmn)，否則英文(en)。

    espeak 預設語音為英文，唸中文會逐字拼錯，故需顯式切換。
    中英混句以「是否含漢字」整句二選一（小修取捨，混句仍非完美）。
    """
    return "cmn" if _has_cjk(text) else "en"


def _split_language_runs(text: str) -> list[tuple[str, str]]:
    """把中英混合文字切成 zh/en 片段，標點與空白附著在前一片段。"""
    runs: list[tuple[str, str]] = []
    current_lang: str | None = None
    current: list[str] = []

    for char in text:
        if _has_cjk(char):
            lang = "zh"
        elif char.isascii() and (char.isalpha() or char.isdigit()):
            lang = "en"
        else:
            lang = current_lang

        if lang is not None and current_lang is not None and lang != current_lang:
            runs.append((current_lang, "".join(current)))
            current = []
        if lang is not None:
            current_lang = lang
        current.append(char)

    if current:
        runs.append((current_lang or "en", "".join(current)))
    return [(lang, chunk) for lang, chunk in runs if chunk.strip()]
