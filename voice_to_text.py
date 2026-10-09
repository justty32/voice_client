import configparser
import logging
import threading
from queue import Empty, Queue

from protocol import payloads as P

log = logging.getLogger(__name__)


class VoiceToText:
    """STT 工作器。從 audio_queue 取 WAV BytesIO，轉譯後將文字放入 stt_output_queue。

    模型在 start() 後的背景執行緒中載入（首次載入可能需要數秒下載模型）。

    stt_event_queue（選用）接收處理結果事件，讓上游得知 STT 的結局：
    模型載入失敗／未載入／轉譯例外 → stt_error；結果空 → stt_empty；
    有文字 → 先把文字放入 stt_output_queue，再發 stt_done。
    未提供（None）時不發事件，手機與舊呼叫者行為不變。
    """

    def __init__(
        self,
        config: configparser.ConfigParser,
        audio_queue: Queue,
        stt_output_queue: Queue,
        stt_event_queue: Queue | None = None,
    ):
        self._audio_queue = audio_queue
        self._stt_output_queue = stt_output_queue
        self._stt_event_queue = stt_event_queue

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
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    # ── Worker ─────────────────────────────────────────────────────────

    def _loop(self):
        self._load_model()
        while self._running:
            try:
                audio_buffer = self._audio_queue.get(timeout=0.2)
            except Empty:
                continue
            self._process_one(audio_buffer)

    def _process_one(self, audio_buffer) -> None:
        """處理一段音訊：轉譯、輸出文字，並回報 stt_event。"""
        if self._model is None:
            # 每段都報，使用者才看得到模型沒有載入
            self._emit_event("stt_error", message="STT 模型未載入")
            return
        try:
            text = self._transcribe(audio_buffer)
        except Exception as exc:
            log.error("STT transcription failed: %s", exc)
            self._emit_event("stt_error", message=str(exc))
            return
        if text:
            self._stt_output_queue.put(text)
            self._emit_event("stt_done")
        else:
            self._emit_event("stt_empty")

    def _emit_event(self, event: str, **extra) -> None:
        if self._stt_event_queue is not None:
            self._stt_event_queue.put(P.stt_event(event, **extra))

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
            self._emit_event("stt_error", message=f"模型載入失敗：{exc}")

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
