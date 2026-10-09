"""
text_to_voice.py — TTS 優先級播放器

架構：
- Dispatcher Thread：管理 heapq 優先佇列，調度語音任務
- pyttsx3：每個語音任務在獨立子 process 中合成播放，打斷時 terminate()
- Kokoro：長駐子 process 懶載入中／英文 ONNX 模型，避免每句重載；
  透過共享取消編號中斷播放。

拆分：語言分段 → tts/language.py；pyttsx3 driver／worker → tts/pyttsx3_worker.py；
Kokoro worker → tts/kokoro_worker.py。本檔保留調度器 AudioPriorityPlayer。

優先級：
- high (0)：立即打斷當前播放，清空佇列中所有 medium/low 任務後優先播出
- medium (1)：正常排隊
- low (2)：排在 medium 之後
"""

import configparser
import heapq
import logging
import multiprocessing as mp
import threading
import time
from pathlib import Path
from queue import Empty, Queue

# tts.* 名稱在此 re-export，維持 `from text_to_voice import ...` 相容。
from tts.kokoro_worker import _kokoro_worker
from tts.language import _has_cjk, _pick_espeak_voice, _split_language_runs  # noqa: F401
from tts.pyttsx3_worker import _pick_tts_driver, _tts_worker

log = logging.getLogger(__name__)


# ── Dispatcher ────────────────────────────────────────────────────────────────

class AudioPriorityPlayer:
    """TTS 優先級播放器。透過 tts_input_queue 接收任務，透過 tts_cmd_queue 接收控制指令。"""

    _PRIORITY = {"high": 0, "medium": 1, "low": 2}
    _POLL = 0.05  # dispatcher 輪詢間隔（秒）
    _KOKORO_MAX_RESTARTS = 1  # D7：Kokoro worker 死亡後最多自動重啟一次

    def __init__(self, config: configparser.ConfigParser, tts_input_queue: Queue, tts_cmd_queue: Queue):
        self._tts_input_queue = tts_input_queue
        self._tts_cmd_queue = tts_cmd_queue

        tts = config["TTS"]
        self._engine = tts.get("engine", "pyttsx3").strip().lower()
        if self._engine not in {"pyttsx3", "kokoro"}:
            raise ValueError(f"Unsupported TTS engine: {self._engine}")
        self._rate = int(tts.get("rate", 180))
        self._volume = float(tts.get("volume", 1.0))
        self._driver = _pick_tts_driver()

        # 顯式用 spawn，讓 Linux/macOS 也與 Windows 行為一致，避免 fork 繼承 PyAudio / Whisper 等資源
        self._ctx = mp.get_context("spawn")
        model_dir = Path(tts.get("kokoro_model_dir", "models/kokoro")).expanduser()
        if not model_dir.is_absolute():
            model_dir = Path(__file__).resolve().parent / model_dir
        self._kokoro_settings = {
            "en_model": str(model_dir / "kokoro-v1.0.onnx"),
            "en_voices": str(model_dir / "voices-v1.0.bin"),
            "zh_model": str(model_dir / "kokoro-v1.1-zh.onnx"),
            "zh_voices": str(model_dir / "voices-v1.1-zh.bin"),
            "zh_config": str(model_dir / "config-v1.1-zh.json"),
            "en_voice": tts.get("kokoro_voice_en", "af_heart"),
            "zh_voice": tts.get("kokoro_voice_zh", "zf_001"),
            "speed": float(tts.get("kokoro_speed", 1.0)),
            "volume": self._volume,
        }

        # heapq: (priority_val, counter, item_dict)
        self._heap: list = []
        self._counter = 0
        self._current: mp.Process | None = None
        self._current_task_id: int | None = None
        self._next_task_id = 1
        self._kokoro_process: mp.Process | None = None
        self._kokoro_tasks = None
        self._kokoro_results = None
        self._kokoro_cancel_through = None
        self._kokoro_restarts = 0     # worker 死亡後已自動重啟的次數（上限 _KOKORO_MAX_RESTARTS）
        self._kokoro_dead = False     # 重啟額度用盡後為 True：之後任務記 log 丟棄

        self._dispatcher_thread: threading.Thread | None = None
        self._running = False

    def start(self):
        if self._engine == "kokoro":
            self._start_kokoro_worker()
        self._running = True
        self._dispatcher_thread = threading.Thread(
            target=self._dispatcher, daemon=True, name="TTS-Dispatcher"
        )
        self._dispatcher_thread.start()

    def stop(self):
        self._running = False
        self._stop_current()
        self._stop_kokoro_worker()
        t = self._dispatcher_thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=1)

    # ── Dispatcher loop ────────────────────────────────────────────────

    def _dispatcher(self):
        while self._running:
            self._check_kokoro_alive()
            self._drain_cmds()
            self._drain_input()
            self._drain_kokoro_results()
            self._maybe_play_next()
            time.sleep(self._POLL)

    def _drain_cmds(self):
        while True:
            try:
                cmd = self._tts_cmd_queue.get_nowait()
                self._handle_cmd(cmd)
            except Empty:
                break

    def _drain_input(self):
        while True:
            try:
                item = self._tts_input_queue.get_nowait()
            except Empty:
                break
            pval = self._PRIORITY.get(item.get("priority", "medium"), 1)
            heapq.heappush(self._heap, (pval, self._counter, item))
            self._counter += 1
            # HIGH priority: interrupt current and purge lower-priority pending
            if pval == 0:
                self._stop_current()
                self._heap = [(p, c, i) for p, c, i in self._heap if p == 0]
                heapq.heapify(self._heap)

    def _maybe_play_next(self):
        if self._heap and not self._is_playing():
            _, _, item = heapq.heappop(self._heap)
            self._play(item)

    # ── Playback ───────────────────────────────────────────────────────

    def _play(self, item: dict):
        text = item.get("text", "").strip()
        if not text:
            return
        if self._engine == "kokoro":
            if self._kokoro_dead:
                log.warning("Kokoro worker 已停用，丟棄 TTS 任務：%.40s…", text)
                return
            task_id = self._next_task_id
            self._next_task_id += 1
            self._current_task_id = task_id
            self._kokoro_tasks.put((task_id, text))
            log.debug("Kokoro TTS [%s] queued task=%s: %.40s…", item.get("priority"), task_id, text)
            return
        self._current = self._ctx.Process(
            target=_tts_worker,
            args=(text, self._rate, self._volume, self._driver),
            daemon=True,
        )
        self._current.start()
        log.debug("TTS [%s] started pid=%s: %.40s…", item.get("priority"), self._current.pid, text)

    def _stop_current(self):
        if self._engine == "kokoro":
            if self._current_task_id is not None and self._kokoro_cancel_through is not None:
                self._kokoro_cancel_through.value = max(
                    self._kokoro_cancel_through.value,
                    self._current_task_id,
                )
                log.debug("Kokoro TTS task %s cancelled.", self._current_task_id)
            self._current_task_id = None
            return
        if self._current and self._current.is_alive():
            self._current.terminate()
            self._current.join(timeout=1)
            log.debug("TTS process terminated.")
        self._current = None

    def _is_playing(self) -> bool:
        if self._engine == "kokoro":
            return self._current_task_id is not None
        return self._current is not None and self._current.is_alive()

    def _start_kokoro_worker(self):
        missing = [
            path for key, path in self._kokoro_settings.items()
            if key in {"en_model", "en_voices", "zh_model", "zh_voices", "zh_config"}
            and not Path(path).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"Kokoro model files missing: {', '.join(missing)}")
        self._kokoro_tasks = self._ctx.Queue()
        self._kokoro_results = self._ctx.Queue()
        self._kokoro_cancel_through = self._ctx.Value("Q", 0)
        self._kokoro_process = self._ctx.Process(
            target=_kokoro_worker,
            args=(
                self._kokoro_tasks,
                self._kokoro_results,
                self._kokoro_cancel_through,
                self._kokoro_settings,
            ),
            daemon=True,
            name="Kokoro-TTS",
        )
        self._kokoro_process.start()

    def _check_kokoro_alive(self):
        """Kokoro worker 存活偵測（B2，D7）。

        worker 意外死亡時：清掉當前任務與待播佇列（否則 _is_playing 永遠為真、TTS 卡死），
        並在額度內自動重啟；額度用盡或重啟失敗則標記 _kokoro_dead，之後 _play 丟棄任務。
        """
        if (self._engine != "kokoro" or self._kokoro_dead
                or self._kokoro_process is None or self._kokoro_process.is_alive()):
            return
        log.error("Kokoro TTS worker 意外結束（exitcode=%s）",
                  getattr(self._kokoro_process, "exitcode", None))
        self._current_task_id = None
        self._heap.clear()
        if self._kokoro_restarts >= self._KOKORO_MAX_RESTARTS:
            self._kokoro_dead = True
            self._kokoro_process = None
            log.error("Kokoro TTS worker 已重啟 %d 次仍死亡，放棄；之後的 TTS 任務將丟棄。",
                      self._kokoro_restarts)
            return
        self._kokoro_restarts += 1
        try:
            self._start_kokoro_worker()
            log.warning("Kokoro TTS worker 已自動重啟（第 %d 次）。", self._kokoro_restarts)
        except Exception as exc:
            self._kokoro_dead = True
            self._kokoro_process = None
            log.error("Kokoro TTS worker 重啟失敗，放棄：%s", exc)

    def _stop_kokoro_worker(self):
        if self._kokoro_process is None:
            return
        if self._kokoro_process.is_alive():
            self._kokoro_tasks.put(None)
            self._kokoro_process.join(timeout=2)
        if self._kokoro_process.is_alive():
            self._kokoro_process.terminate()
            self._kokoro_process.join(timeout=1)
        self._kokoro_process = None

    def _drain_kokoro_results(self):
        if self._engine != "kokoro" or self._kokoro_results is None:
            return
        while True:
            try:
                status, task_id, detail = self._kokoro_results.get_nowait()
            except Empty:
                break
            if status in {"error", "startup_error"}:
                log.error("Kokoro TTS %s: %s", status, detail)
            if task_id == self._current_task_id or status == "startup_error":
                self._current_task_id = None

    # ── Command handling ───────────────────────────────────────────────

    def _handle_cmd(self, cmd: str):
        if cmd == "STOP_SPEECH":
            self._stop_current()
            self._heap.clear()
        elif cmd == "TERMINATE":
            self._running = False
            self._stop_current()
