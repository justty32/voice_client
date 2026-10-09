import configparser
import io
import threading
import time
import wave
from queue import Empty, Queue

import numpy as np
import pyaudio

from protocol import payloads as P


class Recorder:
    """錄音器。透過 recorder_cmd_queue 接收 START/STOP，將 WAV BytesIO 片段放入 audio_queue。

    切片邏輯（皆以「本段曾偵測到語音」為前提，避免把純靜音送進 STT 空轉）：
    1. max_duration > 0 且錄音時長 >= max_duration → 強制切片（連續講話時防止單段過長）
    2. 靜音 >= silence_seconds → 切片（講完一句後的自然停頓）
    講話前的純靜音僅保留約 0.5 秒 pre-roll，不無限累積。
    每次切片後重置計時器與語音旗標，繼續錄音直到收到 STOP。

    STOP 時發 recording_stopped（flushed＝是否有音訊送往 STT）。
    開裝置或錄音迴圈失敗時發 error 事件，並以 min(2**n, 30) 秒退避重試直到 stop()。
    """

    def __init__(
        self,
        config: configparser.ConfigParser,
        recorder_cmd_queue: Queue,
        audio_queue: Queue,
        recorder_event_queue: Queue,
    ):
        self._recorder_cmd_queue = recorder_cmd_queue
        self._audio_queue = audio_queue
        self._recorder_event_queue = recorder_event_queue

        audio = config["AUDIO"]
        self._sample_rate = int(audio.get("sample_rate", 16000))
        self._channels = int(audio.get("channels", 1))
        self._chunk_size = int(audio.get("chunk_size", 1024))
        self._chunk_duration = int(audio.get("chunk_duration", 60))
        self._silence_seconds = float(audio.get("silence_seconds", 1.5))
        self._max_duration = int(audio.get("max_duration", 0))
        self._silence_threshold = float(audio.get("silence_threshold", 300.0))

        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name="Recorder")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    # ── Worker ─────────────────────────────────────────────────────────

    _MAX_BACKOFF = 30.0  # 重試退避上限（秒）

    def _worker(self):
        """開啟音訊裝置並執行 _loop；失敗時回報 error 事件，以指數退避重試直到 stop()。"""
        failures = 0
        while self._running:
            entered, failed = self._run_once()
            if entered:
                failures = 0  # 曾成功進入 _loop：退避從頭計
            if failed:
                failures += 1
                self._interruptible_sleep(min(2 ** failures, self._MAX_BACKOFF))

    def _run_once(self) -> tuple[bool, bool]:
        """開裝置跑一次 _loop，回傳 (是否曾進入 _loop, 是否以例外結束)；例外時 emit error 事件。"""
        pa = None
        stream = None
        entered = False
        failed = False
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._sample_rate,
                input=True,
                frames_per_buffer=self._chunk_size,
            )
            entered = True
            self._loop(stream, pa)
        except Exception as exc:
            failed = True
            self._recorder_event_queue.put(P.recorder_event("error", message=str(exc)))
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa is not None:
                pa.terminate()
        return entered, failed

    def _interruptible_sleep(self, seconds: float) -> None:
        """以 0.1 秒步進等待，stop() 後立即返回。"""
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(0.1)

    def _loop(self, stream, pa):
        recording = False
        frames: list[bytes] = []
        chunk_start = 0.0
        last_sound = 0.0
        had_speech = False  # 本段切片自上次 flush 以來是否偵測到語音

        # 講話前的純靜音只保留少量 pre-roll，避免長時間靜音無限累積記憶體，
        # 同時保住語音起頭不被切掉（約 0.5 秒）。
        preroll_frames = max(1, int(self._sample_rate / self._chunk_size * 0.5))

        while self._running:
            # ── Process pending commands ───────────────────────────────
            try:
                cmd = self._recorder_cmd_queue.get_nowait()
                if cmd == "START" and not recording:
                    recording = True
                    frames = []
                    chunk_start = time.monotonic()
                    last_sound = time.monotonic()
                    had_speech = False
                    self._recorder_event_queue.put({"event": "recording_started"})
                elif cmd == "STOP" and recording:
                    recording = False
                    # 停止時只在確實錄到語音時才送出，避免末段純靜音白跑 STT
                    flushed = had_speech
                    if flushed:
                        self._flush(frames, pa)
                    frames = []
                    had_speech = False
                    # flushed=False 代表沒有音訊送往 STT，下游據此把狀態列復位為待機
                    self._recorder_event_queue.put(
                        P.recorder_event("recording_stopped", flushed=flushed))
            except Empty:
                pass

            if not recording:
                time.sleep(0.02)
                continue

            # ── Read audio chunk ───────────────────────────────────────
            data = stream.read(self._chunk_size, exception_on_overflow=False)
            frames.append(data)
            now = time.monotonic()

            # ── VAD ───────────────────────────────────────────────────
            rms = _rms(data)
            if rms >= self._silence_threshold:
                last_sound = now
                had_speech = True

            # 尚未出現語音：丟棄過舊的靜音，只留 pre-roll，記憶體不無限成長
            if not had_speech and len(frames) > preroll_frames:
                frames = frames[-preroll_frames:]
                chunk_start = now

            elapsed = now - chunk_start
            silence = now - last_sound

            # ── Slice conditions ───────────────────────────────────────
            # 只有「這段確實出現過語音」才因靜音切片，
            # 避免錄音開著但沒人講話時反覆把無聲片段送進 STT 空轉。
            should_slice = (
                (self._max_duration > 0 and had_speech and elapsed >= self._max_duration)
                or (had_speech and silence >= self._silence_seconds)
            )

            if should_slice:
                self._flush(frames, pa)
                frames = []
                chunk_start = now
                last_sound = now
                had_speech = False

    # ── Helpers ────────────────────────────────────────────────────────

    def _flush(self, frames: list[bytes], pa: pyaudio.PyAudio):
        if not frames:
            return
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self._sample_rate)
            wf.writeframes(b"".join(frames))
        buf.seek(0)
        self._audio_queue.put(buf)
        self._recorder_event_queue.put({"event": "chunk_flushed"})


def _rms(data: bytes) -> float:
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(arr ** 2))) if len(arr) else 0.0
