"""HttpClient 單元測試：本地 LLM 模式與 HTTP 轉發模式。

全部以 mock 取代網路（requests.post、LLMClient.chat）；failed_dir 指向暫存目錄。
prompts/llm_system.txt 直接讀檔，不 mock。

執行：python3 -m unittest tests.test_http_client
"""

import configparser
import os
import queue
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http_client import HttpClient


class _FakeSessionManager:
    def __init__(self, history=None):
        self._history = history

    def get_current_session(self):
        if self._history is None:
            return None
        return {"history": [list(m) for m in self._history]}


class _FakeChat:
    """記錄 chat(system_prompt, user_input) 的參數；可設定回傳值或例外。"""

    def __init__(self, reply="回覆", exc=None):
        self.calls = []
        self._reply = reply
        self._exc = exc

    def __call__(self, system_prompt, user_input):
        self.calls.append((system_prompt, user_input))
        if self._exc is not None:
            raise self._exc
        return self._reply


def _make_config(tmp: str, enabled: bool = False, retry: int = 2) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["SERVER"] = {
        "enabled": "true" if enabled else "false",
        "url": "http://127.0.0.1:9/chat",
        "timeout": "1",
        "retry": str(retry),
    }
    cfg["WORKSPACE"] = {"failed_dir": os.path.join(tmp, "failed")}
    cfg["LLM"] = {"model": "fake-llm", "base_url": "http://127.0.0.1:9", "retry": "0"}
    return cfg


class HttpClientTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.failed_dir = os.path.join(self.tmp, "failed")

    def tearDown(self):
        self._tmp.cleanup()

    def make_client(self, history=None, **cfg_kwargs) -> HttpClient:
        return HttpClient(
            _make_config(self.tmp, **cfg_kwargs),
            queue.Queue(),
            queue.Queue(),
            _FakeSessionManager(history),
        )

    def failed_files(self) -> list:
        if not os.path.isdir(self.failed_dir):
            return []
        return [f for f in os.listdir(self.failed_dir) if f.endswith(".json")]


class TestDispatch(HttpClientTestBase):
    def test_local_mode_ignores_payload_without_content(self):
        client = self.make_client()
        client._llm.chat = _FakeChat()
        self.assertIsNone(client._dispatch({"type": "approval"}))
        self.assertEqual(client._llm.chat.calls, [])


class TestPostHttp(HttpClientTestBase):
    def test_retries_then_returns_error_and_backs_up_payload(self):
        client = self.make_client(enabled=True, retry=2)
        with mock.patch("http_client.requests.post", side_effect=ConnectionError("拒絕連線")) as post, \
                mock.patch("http_client.time.sleep"):
            result = client._post_http({"Title": "t", "Content": "hi"})
        self.assertEqual(post.call_count, 3)  # retry + 1
        self.assertEqual(result["type"], "Error")
        self.assertIn("拒絕連線", result["message"])
        self.assertEqual(len(self.failed_files()), 1)

    def test_success_returns_response_json(self):
        client = self.make_client(enabled=True)
        resp = mock.Mock()
        resp.json.return_value = {"type": "ChatReply", "Content": {"full_response": "ok"}}
        with mock.patch("http_client.requests.post", return_value=resp) as post:
            result = client._dispatch({"Title": "t", "Content": "hi"})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(result, {"type": "ChatReply", "Content": {"full_response": "ok"}})
        self.assertEqual(self.failed_files(), [])


class TestCallLocal(HttpClientTestBase):
    def test_empty_history_sends_content_as_is(self):
        client = self.make_client(history=[])
        client._llm.chat = _FakeChat(reply="你好")
        result = client._call_local({"Title": "default", "Content": "本次問題"})
        self.assertEqual(client._llm.chat.calls[0][1], "本次問題")
        self.assertEqual(result, {
            "type": "ChatReply",
            "Title": "default",
            "Content": {"full_response": "你好"},
            "model": "fake-llm",
        })

    def test_history_context_ends_with_current_content(self):
        # B1：歷史迴圈不得覆蓋本次 Content
        history = [
            ["user", "舊問題", "t1"],
            ["assistant", "舊回答", "t2"],
            ["user", "本次問題", "t3"],  # 剛加入的一筆，不列入背景
        ]
        client = self.make_client(history=history)
        client._llm.chat = _FakeChat()
        client._call_local({"Title": "default", "Content": "本次問題"})
        user_input = client._llm.chat.calls[0][1]
        self.assertTrue(user_input.endswith("目前的對話內容：本次問題"), user_input)
        self.assertIn("使用者: 舊問題", user_input)
        self.assertIn("AI助手: 舊回答", user_input)

    def test_chat_exception_returns_error_and_backs_up_payload(self):
        client = self.make_client(history=[])
        client._llm.chat = _FakeChat(exc=RuntimeError("模型掛了"))
        result = client._call_local({"Title": "default", "Content": "問題"})
        self.assertEqual(result, {"type": "Error", "message": "模型掛了"})
        self.assertEqual(len(self.failed_files()), 1)


class TestStopJoins(HttpClientTestBase):
    def test_stop_returns_after_worker_thread_exits(self):
        client = self.make_client()
        client.start()
        thread = client._thread
        self.assertTrue(thread.is_alive())
        client.stop()
        self.assertFalse(thread.is_alive())

    def test_stop_without_start_is_noop(self):
        self.make_client().stop()


if __name__ == "__main__":
    unittest.main()
