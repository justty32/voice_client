import configparser
import queue
import unittest
from pathlib import Path

from text_to_voice import AudioPriorityPlayer, _split_language_runs


def make_config(engine: str = "pyttsx3") -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config["TTS"] = {
        "engine": engine,
        "rate": "180",
        "volume": "0.8",
        "kokoro_model_dir": "models/kokoro",
        "kokoro_voice_en": "af_heart",
        "kokoro_voice_zh": "zf_001",
        "kokoro_speed": "1.1",
    }
    return config


class TestLanguageRuns(unittest.TestCase):
    def test_english_only(self):
        self.assertEqual(_split_language_runs("Hello world."), [("en", "Hello world.")])

    def test_chinese_only(self):
        self.assertEqual(_split_language_runs("你好，世界。"), [("zh", "你好，世界。")])

    def test_mixed_text(self):
        self.assertEqual(
            _split_language_runs("你好 Kokoro 世界"),
            [("zh", "你好 "), ("en", "Kokoro "), ("zh", "世界")],
        )


class TestAudioPriorityPlayerConfig(unittest.TestCase):
    def test_pyttsx3_remains_default_backend(self):
        config = make_config()
        del config["TTS"]["engine"]
        player = AudioPriorityPlayer(config, queue.Queue(), queue.Queue())
        self.assertEqual(player._engine, "pyttsx3")

    def test_kokoro_settings_resolve_from_project_root(self):
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())
        self.assertEqual(player._engine, "kokoro")
        self.assertEqual(player._kokoro_settings["en_voice"], "af_heart")
        self.assertEqual(player._kokoro_settings["zh_voice"], "zf_001")
        self.assertEqual(player._kokoro_settings["speed"], 1.1)
        self.assertTrue(Path(player._kokoro_settings["zh_model"]).is_absolute())

    def test_unknown_engine_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported TTS engine"):
            AudioPriorityPlayer(make_config("unknown"), queue.Queue(), queue.Queue())

    def test_missing_models_fail_before_worker_start(self):
        config = make_config("kokoro")
        config["TTS"]["kokoro_model_dir"] = "models/does-not-exist"
        player = AudioPriorityPlayer(config, queue.Queue(), queue.Queue())
        with self.assertRaisesRegex(FileNotFoundError, "Kokoro model files missing"):
            player._start_kokoro_worker()

    def test_kokoro_stop_marks_current_task_cancelled(self):
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())

        class Value:
            value = 0

        player._kokoro_cancel_through = Value()
        player._current_task_id = 7
        player._stop_current()
        self.assertEqual(player._kokoro_cancel_through.value, 7)
        self.assertIsNone(player._current_task_id)

    def test_kokoro_play_queues_numbered_task(self):
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())
        player._kokoro_tasks = queue.Queue()
        player._play({"text": "你好", "priority": "medium"})
        self.assertEqual(player._current_task_id, 1)
        self.assertEqual(player._kokoro_tasks.get_nowait(), (1, "你好"))

    def test_kokoro_result_only_clears_matching_current_task(self):
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())
        player._kokoro_results = queue.Queue()
        player._current_task_id = 2
        player._kokoro_results.put(("done", 1, None))
        player._drain_kokoro_results()
        self.assertEqual(player._current_task_id, 2)
        player._kokoro_results.put(("done", 2, None))
        player._drain_kokoro_results()
        self.assertIsNone(player._current_task_id)


if __name__ == "__main__":
    unittest.main()
