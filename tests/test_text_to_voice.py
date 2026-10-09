import configparser
import queue
import unittest
from pathlib import Path
from unittest import mock

from speech.text_to_voice import AudioPriorityPlayer, _split_language_runs


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
    def test_default_engine_matches_config_ini(self):
        """缺 engine 鍵時的預設與 config.ini 一致（kokoro）；不啟動 worker。"""
        config = make_config()
        del config["TTS"]["engine"]
        player = AudioPriorityPlayer(config, queue.Queue(), queue.Queue())
        self.assertEqual(player._engine, "kokoro")

    def test_kokoro_settings_resolve_from_project_root(self):
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())
        self.assertEqual(player._engine, "kokoro")
        self.assertEqual(player._kokoro_settings["en_voice"], "af_heart")
        self.assertEqual(player._kokoro_settings["zh_voice"], "zf_001")
        self.assertEqual(player._kokoro_settings["speed"], 1.1)
        self.assertTrue(Path(player._kokoro_settings["zh_model"]).is_absolute())

    def test_relative_model_dir_is_based_on_project_root(self):
        """檔案搬到 speech/ 後，相對 kokoro_model_dir 仍以專案根（而非 speech/）為基準。"""
        root = Path(__file__).resolve().parents[1]
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())
        self.assertEqual(player._kokoro_settings["zh_model"],
                         str(root / "models" / "kokoro" / "kokoro-v1.1-zh.onnx"))
        self.assertEqual(player._kokoro_settings["en_voices"],
                         str(root / "models" / "kokoro" / "voices-v1.0.bin"))

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


class _FakeProcess:
    def __init__(self, alive: bool):
        self.alive = alive
        self.exitcode = None if alive else -9

    def is_alive(self):
        return self.alive


class TestKokoroLiveness(unittest.TestCase):
    """B2／D7：Kokoro worker 死亡 → 清狀態、自動重啟一次，再死則放棄並丟棄任務。"""

    def _dead_player(self):
        player = AudioPriorityPlayer(make_config("kokoro"), queue.Queue(), queue.Queue())
        player._kokoro_process = _FakeProcess(alive=False)
        player._kokoro_tasks = queue.Queue()
        player._current_task_id = 5
        player._heap = [(1, 0, {"text": "待播", "priority": "medium"})]
        return player

    def test_alive_worker_is_left_alone(self):
        player = self._dead_player()
        player._kokoro_process = _FakeProcess(alive=True)
        with mock.patch.object(player, "_start_kokoro_worker") as start:
            player._check_kokoro_alive()
        start.assert_not_called()
        self.assertEqual(player._current_task_id, 5)
        self.assertEqual(len(player._heap), 1)

    def test_first_death_clears_state_and_restarts_once(self):
        player = self._dead_player()

        def _restart():
            player._kokoro_process = _FakeProcess(alive=True)

        with mock.patch.object(player, "_start_kokoro_worker", side_effect=_restart) as start, \
                self.assertLogs("speech.text_to_voice", level="ERROR"):
            player._check_kokoro_alive()
            player._check_kokoro_alive()  # 重啟後存活：不再重啟
        start.assert_called_once_with()
        self.assertIsNone(player._current_task_id)
        self.assertEqual(player._heap, [])
        self.assertEqual(player._kokoro_restarts, 1)
        self.assertFalse(player._kokoro_dead)

    def test_second_death_gives_up_and_drops_tasks(self):
        player = self._dead_player()
        with mock.patch.object(player, "_start_kokoro_worker",
                               side_effect=lambda: setattr(player, "_kokoro_process",
                                                           _FakeProcess(alive=False))) as start, \
                self.assertLogs("speech.text_to_voice", level="ERROR"):
            player._check_kokoro_alive()   # 第一次死亡 → 重啟（新 worker 也立刻死）
            player._check_kokoro_alive()   # 第二次死亡 → 放棄
            player._check_kokoro_alive()   # 已放棄：不再動作
        self.assertEqual(start.call_count, 1)
        self.assertTrue(player._kokoro_dead)

        tasks = queue.Queue()
        player._kokoro_tasks = tasks
        with self.assertLogs("speech.text_to_voice", level="WARNING"):
            player._play({"text": "你好", "priority": "medium"})
        self.assertTrue(tasks.empty())
        self.assertIsNone(player._current_task_id)
        self.assertFalse(player._is_playing())

    def test_restart_failure_marks_dead(self):
        player = self._dead_player()
        with mock.patch.object(player, "_start_kokoro_worker",
                               side_effect=FileNotFoundError("Kokoro model files missing")), \
                self.assertLogs("speech.text_to_voice", level="ERROR"):
            player._check_kokoro_alive()
        self.assertTrue(player._kokoro_dead)
        self.assertIsNone(player._kokoro_process)

    def test_pyttsx3_engine_skips_check(self):
        player = AudioPriorityPlayer(make_config("pyttsx3"), queue.Queue(), queue.Queue())
        player._kokoro_process = _FakeProcess(alive=False)
        with mock.patch.object(player, "_start_kokoro_worker") as start:
            player._check_kokoro_alive()
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
