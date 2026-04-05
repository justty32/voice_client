import configparser
import logging
import queue
import threading
from queue import Empty, Queue

from utils.llm_client import LLMClient
from utils.prompt_loader import load_prompt

log = logging.getLogger(__name__)


class SLMProcessor:
    """本地 SLM 預處理中心。

    兩條處理線：
    - Pre (_pre_loop)：累積文字 → flush 時用 SLM 清洗 → 輸出 payload
    - Post (_post_loop)：接收 LLM 回覆 → SLM 生成摘要 → 輸出 TTS 任務
    """

    def __init__(
        self,
        config: configparser.ConfigParser,
        slm_input_queue: Queue,
        slm_cmd_queue: Queue,
        slm_output_queue: Queue,
    ):
        self._slm_input_queue = slm_input_queue
        self._slm_cmd_queue = slm_cmd_queue
        self._slm_output_queue = slm_output_queue

        slm = config["SLM"]
        self._enabled = slm.getboolean("enabled", True)
        model = slm.get("model", "qwen2.5:1.5b")
        base_url = slm.get("base_url", "http://localhost:11434")

        self._llm = LLMClient(model, base_url)
        self._concat_prompt = load_prompt("slm_concat")
        self._summary_prompt = load_prompt("slm_summary")

        self._buffer: list[str] = []
        self._summary_queue: queue.Queue = queue.Queue()
        self._pre_thread: threading.Thread | None = None
        self._post_thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._pre_thread = threading.Thread(target=self._pre_loop, daemon=True, name="SLM-Pre")
        self._post_thread = threading.Thread(target=self._post_loop, daemon=True, name="SLM-Post")
        self._pre_thread.start()
        self._post_thread.start()

    def stop(self):
        self._running = False

    # ── Pre-processing ─────────────────────────────────────────────────

    def _pre_loop(self):
        while self._running:
            # Commands take priority over input
            try:
                cmd = self._slm_cmd_queue.get_nowait()
                self._handle_cmd(cmd)
            except Empty:
                pass

            try:
                item = self._slm_input_queue.get(timeout=0.1)
                if item.get("type") == "text" and item.get("text", "").strip():
                    self._buffer.append(item["text"])
            except Empty:
                pass

    def _handle_cmd(self, cmd: dict):
        op = cmd.get("cmd")
        if op == "flush":
            self._flush(msg_type=cmd.get("msg_type", "TextChat"))
        elif op == "summary":
            text = cmd.get("text", "").strip()
            if text:
                self._summary_queue.put({"text": text, "title": cmd.get("title", "")})
        elif op == "peek":
            if self._buffer:
                lines = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(self._buffer))
                text = f"[暫存區 · {len(self._buffer)} 筆]\n{lines}"
            else:
                text = "[暫存區是空的]"
            self._slm_output_queue.put({"type": "buffer_peek", "text": text})

    def _flush(self, msg_type: str = "TextChat"):
        if not self._buffer:
            return
        combined = " ".join(self._buffer)
        self._buffer.clear()

        if self._enabled:
            self._slm_output_queue.put({"type": "status", "text": "SLM處理中"})
            processed = self._clean(combined)
        else:
            processed = combined
        if not processed.strip():
            return

        self._slm_output_queue.put({
            "type": "payload",
            "payload": {
                "Title": "",        # Main Loop fills in
                "Content": processed,
                "Metadata": {},     # Main Loop fills in
            },
        })

    def _clean(self, text: str) -> str:
        """用 SLM 清洗語音辨識碎片，失敗時回傳原文。"""
        try:
            return self._llm.chat(self._concat_prompt, text) or text
        except Exception as exc:
            log.warning("SLM concat failed, using raw text: %s", exc)
            return text

    # ── Post-processing ────────────────────────────────────────────────

    def _post_loop(self):
        while self._running:
            try:
                task = self._summary_queue.get(timeout=0.1)
            except Empty:
                continue

            if not self._enabled:
                continue

            text = task.get("text", "")
            try:
                self._slm_output_queue.put({"type": "status", "text": "SLM摘要中"})
                summary = self._llm.chat(self._summary_prompt, text)
                if summary.strip():
                    self._slm_output_queue.put({
                        "type": "summary",
                        "text": summary,
                        "model": self._model,
                    })
            except Exception as exc:
                log.warning("SLM summary failed: %s", exc)
            finally:
                self._slm_output_queue.put({"type": "status", "text": "待機"})
