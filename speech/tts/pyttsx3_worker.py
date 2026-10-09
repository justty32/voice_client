"""tts/pyttsx3_worker.py — pyttsx3 平台 driver 選擇與子 process 合成播放 worker。

每個語音任務在獨立子 process 中執行，打斷時由播放器 terminate()。
"""

import sys

from speech.tts.language import _pick_espeak_voice


def _pick_tts_driver() -> str | None:
    if sys.platform == "win32":
        return "sapi5"
    if sys.platform == "darwin":
        return "nsss"
    return "espeak"


def _tts_worker(text: str, rate: int, volume: float, driver: str | None):
    """在獨立子 process 中合成並播放語音。此函式必須位於模組頂層以支援 spawn。"""
    try:
        import pyttsx3
        engine = pyttsx3.init(driverName=driver) if driver else pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        # 僅 espeak 需要依語言切 voice；其他 driver（sapi5/nsss）沿用系統預設。
        if driver == "espeak":
            try:
                engine.setProperty("voice", _pick_espeak_voice(text))
            except Exception:
                pass  # 切換失敗時退回預設語音，至少英文可用
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        print(f"[tts-worker] {type(exc).__name__}: {exc}", file=sys.stderr)
