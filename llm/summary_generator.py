import configparser
import logging
import threading
from queue import Empty, Queue

from llm.llm_client import LLMClient
from utils.prompt_loader import load_prompt

log = logging.getLogger(__name__)

class SummaryGenerator:
    """接收 LLM 回覆並生成摘要的元件。

    輸出（summary_output_queue）：{"type":"status"} 狀態、{"type":"summary"} 摘要；
    例外或空摘要時改出 {"type":"summary_failed","message","text"}（text＝原文）。
    """

    def __init__(
        self,
        config: configparser.ConfigParser,
        summary_queue: Queue,
        summary_output_queue: Queue,
    ):
        self._summary_queue = summary_queue
        self._output_queue = summary_output_queue

        slm = config["SLM"]
        self._enabled = slm.getboolean("enabled", True)
        self._model = slm.get("model", "gemma3:1b")
        base_url = slm.get("base_url", "http://localhost:11434")
        api_key = slm.get("api_key", "")
        retry = int(slm.get("retry", "3"))

        self._llm = LLMClient(self._model, base_url, api_key=api_key, max_retries=retry)
        self._summary_prompt = load_prompt("slm_summary")

        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SummaryGenerator")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    def _loop(self):
        while self._running:
            try:
                task = self._summary_queue.get(timeout=0.1)
            except Empty:
                continue

            if not self._enabled:
                continue

            text = task.get("text", "")
            try:
                self._output_queue.put({"type": "status", "text": "SLM摘要中"})
                summary = self._llm.chat(self._summary_prompt, text)
                if summary and summary.strip():
                    self._output_queue.put({
                        "type": "summary",
                        "text": summary,
                        "model": self._model,
                    })
                else:
                    self._put_failed("空摘要", text)
            except Exception as exc:
                log.warning("SLM summary failed: %s", exc)
                self._put_failed(str(exc), text)
            finally:
                self._output_queue.put({"type": "status", "text": "待機"})

    def _put_failed(self, message: str, text: str) -> None:
        """摘要失敗（例外或空摘要）：帶回原文，讓下游改播原文而非無聲。"""
        self._output_queue.put({"type": "summary_failed", "message": message, "text": text})
