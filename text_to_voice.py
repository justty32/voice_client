"""
text_to_voice.py — TTS 優先級播放器

架構：
- Dispatcher Thread：管理 heapq 優先佇列，調度語音任務
- TTS Worker Process：每個語音任務在獨立子 process 中執行，避免 GIL 阻塞
  子 process 以 pyttsx3 合成並播放，完成後自動結束。
  打斷時直接 terminate() 子 process。

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
from queue import Empty, Queue

log = logging.getLogger(__name__)


# ── TTS Worker (runs in subprocess) ───────────────────────────────────────────

def _tts_worker(text: str, rate: int, volume: float):
    """在獨立子 process 中合成並播放語音。此函式必須位於模組頂層以支援 spawn。"""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        pass  # 子 process 不寫 log，靜默失敗


# ── Dispatcher ────────────────────────────────────────────────────────────────

class AudioPriorityPlayer:
    """TTS 優先級播放器。透過 tts_input_queue 接收任務，透過 tts_cmd_queue 接收控制指令。"""

    _PRIORITY = {"high": 0, "medium": 1, "low": 2}
    _POLL = 0.05  # dispatcher 輪詢間隔（秒）

    def __init__(self, config: configparser.ConfigParser, tts_input_queue: Queue, tts_cmd_queue: Queue):
        self._tts_input_queue = tts_input_queue
        self._tts_cmd_queue = tts_cmd_queue

        tts = config["TTS"]
        self._rate = int(tts.get("rate", 180))
        self._volume = float(tts.get("volume", 1.0))

        # heapq: (priority_val, counter, item_dict)
        self._heap: list = []
        self._counter = 0
        self._current: mp.Process | None = None

        self._dispatcher_thread: threading.Thread | None = None
        self._running = False
        self._muted = False

    def start(self):
        self._running = True
        self._dispatcher_thread = threading.Thread(
            target=self._dispatcher, daemon=True, name="TTS-Dispatcher"
        )
        self._dispatcher_thread.start()

    def stop(self):
        self._running = False
        self._stop_current()

    # ── Dispatcher loop ────────────────────────────────────────────────

    def _dispatcher(self):
        while self._running:
            self._drain_cmds()
            self._drain_input()
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
            if self._muted:
                continue
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
        self._current = mp.Process(
            target=_tts_worker,
            args=(text, self._rate, self._volume),
            daemon=True,
        )
        self._current.start()
        log.debug("TTS [%s] started pid=%s: %.40s…", item.get("priority"), self._current.pid, text)

    def _stop_current(self):
        if self._current and self._current.is_alive():
            self._current.terminate()
            self._current.join(timeout=1)
            log.debug("TTS process terminated.")
        self._current = None

    def _is_playing(self) -> bool:
        return self._current is not None and self._current.is_alive()

    # ── Command handling ───────────────────────────────────────────────

    def _handle_cmd(self, cmd: str):
        if cmd == "STOP_SPEECH":
            self._stop_current()
            self._heap.clear()
        elif cmd == "MUTE":
            self._muted = True
            self._stop_current()
            self._heap.clear()
        elif cmd == "UNMUTE":
            self._muted = False
        elif cmd == "TERMINATE":
            self._running = False
            self._stop_current()
