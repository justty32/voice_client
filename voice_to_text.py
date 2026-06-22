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
        language = stt.get("language", "auto").strip().lower()
        self._language = None if language in ("", "auto", "detect") else language
        self._beam_size = int(stt.get("beam_size", 5))
        self._vad_filter = stt.getboolean("vad_filter", True)
        initial_prompt = stt.get("initial_prompt", "").strip()
        self._initial_prompt = initial_prompt or None

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

    def _preload_cuda_libs(self):
        """讓 GPU 轉譯找得到 cuBLAS。

        CTranslate2（faster-whisper 後端）4.x 針對 CUDA 12 編譯，runtime 需要
        ``libcublas.so.12``。系統若是 CUDA 13（只提供 ``libcublas.so.13``），GPU
        轉譯時會報 ``libcublas.so.12 is not found``。我們把 pip 安裝的
        ``nvidia-cublas-cu12`` 預載進本行程，CTranslate2 即可依 soname 找到它，
        不需污染系統 CUDA 或設定 ``LD_LIBRARY_PATH``。

        僅在 device 為 cuda 時嘗試；失敗只記 warning 不中斷（CPU 模式或未安裝
        該套件時照常運作）。
        """
        if "cuda" not in self._device:
            return
        try:
            import ctypes
            import os
            import nvidia.cublas as cublas_pkg

            libdir = os.path.join(list(cublas_pkg.__path__)[0], "lib")
            # 先載 cublasLt（cublas 依賴它），用 RTLD_GLOBAL 讓後續 dlopen 看得到
            for name in ("libcublasLt.so.12", "libcublas.so.12"):
                ctypes.CDLL(os.path.join(libdir, name), mode=ctypes.RTLD_GLOBAL)
            log.info("Preloaded CUDA 12 cuBLAS from %s", libdir)
        except Exception as exc:
            log.warning(
                "cuBLAS 預載失敗，GPU 轉譯可能報 libcublas.so.12 not found"
                "（CUDA 13 系統請 pip 安裝 nvidia-cublas-cu12）：%s", exc)

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
            self._preload_cuda_libs()
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
            initial_prompt=self._initial_prompt,
        )
        return "".join(seg.text for seg in segments).strip()
