"""手機測試的替身元件與 `make_state()`（不需 fastapi；`_mobile_helpers.py` 另加 TestClient 工具）。

替身不載入 Whisper、不連 LLM；`make_config()` 把所有落盤路徑指向 tmp。
"""

import configparser
import os
import queue
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mobile.state import build_mobile_state  # noqa: E402


class FakeVoiceToText:
    """不載入模型；測試可直接往 stt_q 放字串模擬辨識結果。"""

    def __init__(self, cfg, audio_q, stt_q, stt_event_queue=None):
        self.audio_q = audio_q
        self.stt_q = stt_q
        self.stt_event_q = stt_event_queue

    def start(self):
        pass

    def stop(self):
        pass


class FakeHttpClient:
    """從 send_queue 取 payload，立即回 ChatReply「回覆:<Content>」到 recv_queue。"""

    def __init__(self, cfg, send_q, recv_q, session_manager):
        self.send_q = send_q
        self.recv_q = recv_q
        self.sent: list[dict] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="FakeHttpClient")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _loop(self):
        while self._running:
            try:
                payload = self.send_q.get(timeout=0.02)
            except queue.Empty:
                continue
            self.sent.append(payload)
            self.recv_q.put({
                "type": "ChatReply",
                "Content": {"full_response": "回覆:" + payload["Content"]},
            })


class FakeSummary:
    def __init__(self, cfg, summary_q, summary_output_q):
        pass

    def start(self):
        pass

    def stop(self):
        pass


def make_config(tmp: str) -> configparser.ConfigParser:
    """所有落盤路徑指向 tmp；SLM 停用（回覆直接 TTS，不走摘要）。"""
    cfg = configparser.ConfigParser()
    out = os.path.join(tmp, "output")
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(out, ".sessions.json"),
        "deleted_sessions_dir": os.path.join(out, "deleted"),
        "export_file": os.path.join(out, "export.json"),
        "log_file": os.path.join(out, "system.log"),
        "failed_dir": os.path.join(out, "failed"),
    }
    cfg["SLM"] = {"enabled": "false"}
    return cfg


def make_state(tmp: str):
    return build_mobile_state(
        make_config(tmp),
        voice_to_text_cls=FakeVoiceToText,
        http_client_cls=FakeHttpClient,
        summary_cls=FakeSummary,
        setup_logging=False,
    )
