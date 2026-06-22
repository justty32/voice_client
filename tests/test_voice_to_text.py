"""VoiceToText configuration tests.

執行：python3 -m unittest tests.test_voice_to_text
"""

import configparser
import os
import sys
import unittest
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_to_text import VoiceToText


def make_config(language: str, initial_prompt: str | None = None) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["STT"] = {
        "model_size": "tiny",
        "device": "cpu",
        "compute_type": "int8",
        "language": language,
        "beam_size": "5",
        "vad_filter": "true",
    }
    if initial_prompt is not None:
        cfg["STT"]["initial_prompt"] = initial_prompt
    return cfg


class TestVoiceToTextConfig(unittest.TestCase):
    def test_auto_language_uses_whisper_detection(self):
        vtt = VoiceToText(make_config("auto"), Queue(), Queue())
        self.assertIsNone(vtt._language)

    def test_blank_language_uses_whisper_detection(self):
        vtt = VoiceToText(make_config(""), Queue(), Queue())
        self.assertIsNone(vtt._language)

    def test_explicit_language_is_preserved(self):
        vtt = VoiceToText(make_config("en"), Queue(), Queue())
        self.assertEqual(vtt._language, "en")

    def test_initial_prompt_defaults_to_none(self):
        vtt = VoiceToText(make_config("zh"), Queue(), Queue())
        self.assertIsNone(vtt._initial_prompt)

    def test_blank_initial_prompt_is_none(self):
        vtt = VoiceToText(make_config("zh", "   "), Queue(), Queue())
        self.assertIsNone(vtt._initial_prompt)

    def test_initial_prompt_is_preserved(self):
        vtt = VoiceToText(make_config("zh", "以下是繁體中文的句子。"), Queue(), Queue())
        self.assertEqual(vtt._initial_prompt, "以下是繁體中文的句子。")

    def test_preload_cuda_libs_noop_on_cpu(self):
        # CPU 模式不該嘗試載入任何 CUDA 庫，且絕不拋例外。
        cfg = make_config("zh")
        cfg["STT"]["device"] = "cpu"
        vtt = VoiceToText(cfg, Queue(), Queue())
        vtt._preload_cuda_libs()  # 應為安全 no-op


if __name__ == "__main__":
    unittest.main()
