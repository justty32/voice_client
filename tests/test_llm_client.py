"""llm.llm_client.LLMClient 單元測試：重試次數語意與回傳值。

以 mock 取代 requests.post 與 time.sleep；不連網、不等待。

執行：python3 -m unittest tests.test_llm_client
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.llm_client import LLMClient


def _ok_response(text: str) -> mock.Mock:
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    resp.raise_for_status.return_value = None
    return resp


class TestLLMClient(unittest.TestCase):
    def test_success_returns_content_and_sends_messages(self):
        client = LLMClient("m", "http://host/v1/", api_key="k", max_retries=2)
        with mock.patch("llm.llm_client.requests.post", return_value=_ok_response("答案")) as post:
            self.assertEqual(client.chat("系統", "問題"), "答案")
        self.assertEqual(post.call_count, 1)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://host/v1/chat/completions")
        self.assertEqual(kwargs["json"]["messages"], [
            {"role": "system", "content": "系統"},
            {"role": "user", "content": "問題"},
        ])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer k")

    def test_connection_error_attempts_max_retries_plus_one(self):
        client = LLMClient("m", "http://host/v1", max_retries=2)
        err = requests.exceptions.ConnectionError("down")
        with mock.patch("llm.llm_client.requests.post", side_effect=err) as post, \
                mock.patch("llm.llm_client.time.sleep"):
            with self.assertRaises(requests.exceptions.ConnectionError):
                client.chat("", "問題")
        self.assertEqual(post.call_count, 3)

    def test_zero_retries_still_attempts_once(self):
        client = LLMClient("m", "http://host/v1", max_retries=0)
        err = requests.exceptions.ConnectionError("down")
        with mock.patch("llm.llm_client.requests.post", side_effect=err) as post, \
                mock.patch("llm.llm_client.time.sleep") as sleep:
            with self.assertRaises(requests.exceptions.ConnectionError):
                client.chat("", "問題")
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_recovers_after_transient_failure(self):
        client = LLMClient("m", "http://host/v1", max_retries=1)
        err = requests.exceptions.ConnectionError("down")
        with mock.patch("llm.llm_client.requests.post",
                        side_effect=[err, _ok_response("第二次成功")]) as post, \
                mock.patch("llm.llm_client.time.sleep"):
            self.assertEqual(client.chat("", "問題"), "第二次成功")
        self.assertEqual(post.call_count, 2)
        # 無系統提示時只送 user 訊息
        self.assertEqual(post.call_args.kwargs["json"]["messages"], [{"role": "user", "content": "問題"}])


if __name__ == "__main__":
    unittest.main()
