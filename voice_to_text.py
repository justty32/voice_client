import configparser
import logging
import threading
from queue import Empty, Queue

log = logging.getLogger(__name__)


class VoiceToText:
    """STT 工作器。從 audio_queue 取 WAV BytesIO，轉譯後將文字放入 stt_output_queue。

    模型在 start() 後的背景執行緒中載入（首次載入可能需要數秒下載模型）。
    """

    def __init__(self, config: configparser.ConfigParser, audio_queue: Queue, stt_output_queue: Queue):
        self._audio_queue = audio_queue
        self._stt_output_queue = stt_output_queue

        stt = config["STT"]
        self._model_size = stt.get("model_size", "base")
        self._device = stt.get("device", "cpu")
        self._compute_type = stt.get("compute_type", "int8")
        self._language = stt.get("language", "zh")
        self._beam_size = int(stt.get("beam_size", 5))
        self._vad_filter = stt.getboolean("vad_filter", True)

        self._model = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="VoiceToText")
        self._thread.start()

    def stop(self):
        self._running = False

    # ── Worker ─────────────────────────────────────────────────────────

    def _loop(self):
        self._load_model()
        while self._running:
            try:
                audio_buffer = self._audio_queue.get(timeout=0.2)
            except Empty:
                continue
            try:
                text = self._transcribe(audio_buffer)
                if text:
                    self._stt_output_queue.put(text)
            except Exception as exc:
                log.error("STT transcription failed: %s", exc)

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
            log.info("Loading Whisper model '%s' on %s (%s)…",
                     self._model_size, self._device, self._compute_type)
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            log.info("Whisper model loaded.")
        except Exception as exc:
            log.error("Failed to load Whisper model: %s", exc)

    def _transcribe(self, audio_buffer) -> str:
        if self._model is None:
            return ""
        segments, _ = self._model.transcribe(
            audio_buffer,
            beam_size=self._beam_size,
            language=self._language,
            vad_filter=self._vad_filter,
        )
        return "".join(seg.text for seg in segments).strip()
