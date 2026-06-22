"""
text_to_voice.py — TTS 優先級播放器

架構：
- Dispatcher Thread：管理 heapq 優先佇列，調度語音任務
- pyttsx3：每個語音任務在獨立子 process 中合成播放，打斷時 terminate()
- Kokoro：長駐子 process 懶載入中／英文 ONNX 模型，避免每句重載；
  透過共享取消編號中斷播放。

優先級：
- high (0)：立即打斷當前播放，清空佇列中所有 medium/low 任務後優先播出
- medium (1)：正常排隊
- low (2)：排在 medium 之後
"""

import configparser
import heapq
import logging
import multiprocessing as mp
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

log = logging.getLogger(__name__)


def _pick_tts_driver() -> str | None:
    if sys.platform == "win32":
        return "sapi5"
    if sys.platform == "darwin":
        return "nsss"
    return "espeak"


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


# ── TTS Worker (runs in subprocess) ───────────────────────────────────────────

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


def _kokoro_worker(
    task_queue,
    result_queue,
    cancel_through,
    settings: dict,
):
    """長駐 Kokoro worker：懶載入模型、合成中英片段並以 PyAudio 播放。"""
    try:
        import numpy as np
        import pyaudio
        from kokoro_onnx import Kokoro
        from misaki import zh
    except Exception as exc:
        result_queue.put(("startup_error", 0, f"{type(exc).__name__}: {exc}"))
        return

    models: dict[str, object] = {}
    zh_g2p = None

    def load_model(lang: str):
        nonlocal zh_g2p
        if lang in models:
            return models[lang]
        if lang == "zh":
            zh_g2p = zh.ZHG2P(version="1.1")
            models[lang] = Kokoro(
                settings["zh_model"],
                settings["zh_voices"],
                vocab_config=settings["zh_config"],
            )
        else:
            models[lang] = Kokoro(settings["en_model"], settings["en_voices"])
        return models[lang]

    while True:
        task = task_queue.get()
        if task is None:
            break
        task_id, text = task
        try:
            chunks = []
            sample_rate = 24000
            for lang, chunk in _split_language_runs(text):
                if task_id <= cancel_through.value:
                    break
                kokoro = load_model(lang)
                if lang == "zh":
                    phonemes, _ = zh_g2p(chunk)
                    samples, sample_rate = kokoro.create(
                        phonemes,
                        voice=settings["zh_voice"],
                        speed=settings["speed"],
                        is_phonemes=True,
                    )
                else:
                    samples, sample_rate = kokoro.create(
                        chunk,
                        voice=settings["en_voice"],
                        speed=settings["speed"],
                        lang="en-us",
                    )
                chunks.append(samples)

            if chunks and task_id > cancel_through.value:
                audio = np.concatenate(chunks).astype(np.float32, copy=False)
                volume = settings["volume"]
                if volume != 1.0:
                    audio = np.clip(audio * volume, -1.0, 1.0)
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=sample_rate,
                    output=True,
                )
                try:
                    frame_size = 2048
                    for offset in range(0, len(audio), frame_size):
                        if task_id <= cancel_through.value:
                            break
                        stream.write(audio[offset:offset + frame_size].tobytes())
                finally:
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
            result_queue.put(("done", task_id, None))
        except Exception as exc:
            result_queue.put(("error", task_id, f"{type(exc).__name__}: {exc}"))


# ── Dispatcher ────────────────────────────────────────────────────────────────

class AudioPriorityPlayer:
    """TTS 優先級播放器。透過 tts_input_queue 接收任務，透過 tts_cmd_queue 接收控制指令。"""

    _PRIORITY = {"high": 0, "medium": 1, "low": 2}
    _POLL = 0.05  # dispatcher 輪詢間隔（秒）

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

        self._dispatcher_thread: threading.Thread | None = None
        self._running = False
        self._muted = False

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

    # ── Dispatcher loop ────────────────────────────────────────────────

    def _dispatcher(self):
        while self._running:
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
        if self._engine == "kokoro":
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
        elif cmd == "MUTE":
            self._muted = True
            self._stop_current()
            self._heap.clear()
        elif cmd == "UNMUTE":
            self._muted = False
        elif cmd == "TERMINATE":
            self._running = False
            self._stop_current()
