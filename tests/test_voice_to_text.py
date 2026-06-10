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


def make_config(language: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["STT"] = {
        "model_size": "tiny",
        "device": "cpu",
        "compute_type": "int8",
        "language": language,
        "beam_size": "5",
        "vad_filter": "true",
    }
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


if __name__ == "__main__":
    unittest.main()
