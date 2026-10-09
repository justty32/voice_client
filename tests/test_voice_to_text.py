"""VoiceToText configuration tests.

執行：python3 -m unittest tests.test_voice_to_text
"""

import configparser
import os
import sys
import unittest
from queue import Queue
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speech.voice_to_text import VoiceToText


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

    def test_initial_prompt_default_matches_config_ini(self):
        """缺 initial_prompt 鍵時用與 config.ini 相同的預設提示；明確留空才停用（見下一案）。"""
        vtt = VoiceToText(make_config("zh"), Queue(), Queue())
        self.assertEqual(vtt._initial_prompt, "以下是繁體中文的句子。")

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


class _FakeSeg:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self, texts=(), exc=None):
        self._texts = texts
        self._exc = exc

    def transcribe(self, _audio, **_kwargs):
        if self._exc is not None:
            raise self._exc
        return [_FakeSeg(t) for t in self._texts], None


def _drain(q):
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


class TestVoiceToTextSttEvent(unittest.TestCase):
    """stt_event：STT 的每種結局都回報上游（B7、B8）。"""

    def _make(self):
        out, events = Queue(), Queue()
        vtt = VoiceToText(make_config("zh"), Queue(), out, stt_event_queue=events)
        return vtt, out, events

    def test_load_model_failure_reports_stt_error(self):
        vtt, _out, events = self._make()
        fake_fw = mock.MagicMock()
        fake_fw.WhisperModel.side_effect = RuntimeError("找不到模型")
        with mock.patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            vtt._load_model()
        self.assertIsNone(vtt._model)
        evs = _drain(events)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "stt_error")
        self.assertIn("找不到模型", evs[0]["message"])

    def test_model_not_loaded_reports_each_segment(self):
        vtt, out, events = self._make()
        vtt._process_one(object())
        vtt._process_one(object())
        self.assertTrue(out.empty())
        self.assertEqual(_drain(events), [{"event": "stt_error", "message": "STT 模型未載入"}] * 2)

    def test_empty_result_reports_stt_empty(self):
        vtt, out, events = self._make()
        vtt._model = _FakeModel(texts=("  ",))
        vtt._process_one(object())
        self.assertTrue(out.empty())
        self.assertEqual(_drain(events), [{"event": "stt_empty"}])

    def test_text_result_outputs_then_reports_done(self):
        vtt, out, events = self._make()
        vtt._model = _FakeModel(texts=("你好", "世界"))
        vtt._process_one(object())
        self.assertEqual(_drain(out), ["你好世界"])
        self.assertEqual(_drain(events), [{"event": "stt_done"}])

    def test_transcribe_exception_reports_stt_error(self):
        vtt, out, events = self._make()
        vtt._model = _FakeModel(exc=RuntimeError("cuda 爆了"))
        vtt._process_one(object())
        self.assertTrue(out.empty())
        self.assertEqual(_drain(events), [{"event": "stt_error", "message": "cuda 爆了"}])

    def test_without_event_queue_stays_silent(self):
        """未提供 stt_event_queue（手機／舊呼叫者）時不發事件也不拋例外。"""
        out = Queue()
        vtt = VoiceToText(make_config("zh"), Queue(), out)
        vtt._process_one(object())
        vtt._model = _FakeModel(texts=("hi",))
        vtt._process_one(object())
        self.assertEqual(_drain(out), ["hi"])


if __name__ == "__main__":
    unittest.main()
