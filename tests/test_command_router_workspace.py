"""modules.CommandRouter 工作區指令單元測試（Task 3）。

執行：python3 -m unittest tests.test_command_router_workspace
"""

import configparser
import os
import queue
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from session_manager import SessionManager


# ── 共用 fixtures ──────────────────────────────────────────────────────────────


def make_sm(tmp: str) -> SessionManager:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    sm = SessionManager(cfg)
    sm.new_session("default")
    return sm


def make_router(tmp: str, sm=None) -> tuple:
    """回傳 (router, wm, sm)；export_dir 指向 tmp。"""
    wm = WorkspaceManager()
    if sm is None:
        sm = make_sm(tmp)
    router = CommandRouter(workspace_manager=wm, session_manager=sm, export_dir=tmp)
    return router, wm, sm


def drain(router) -> list:
    """取出所有 outbox 訊息，回傳 list[Message]。"""
    msgs = []
    while True:
        try:
            msgs.append(router.outbox.get_nowait())
        except queue.Empty:
            break
    return msgs


def cmd(router, cmd_str: str, args: list = None):
    """送出一個 /cmd 指令並回傳所有輸出訊息。"""
    payload = {"cmd": cmd_str, "args": args if args is not None else []}
    router.handle(Message(topic="commands", payload=payload))
    return drain(router)


# ── Test classes ───────────────────────────────────────────────────────────────


class TestWsCommand(unittest.TestCase):
    """Test 1-2: /ws 列出工作區 + 切換"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ws_no_args_lists_workspaces(self):
        """Test 1: /ws 無參數列出 buffer、stt 並標示當前，chat 顯示真實筆數"""
        msgs = cmd(self.router, "/ws")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")
        text = msgs[0].payload["text"]
        self.assertIn("buffer", text)
        self.assertIn("stt", text)
        # 當前工作區 buffer 應有標示
        self.assertIn("當前", text)
        # chat 應出現並顯示筆數（不再是階段④佔位訊息）
        self.assertIn("chat", text)
        self.assertNotIn("階段④", text)

    def test_ws_no_args_shows_counts(self):
        """Test 1b: /ws 無參數顯示各工作區筆數"""
        # 在 buffer 加一筆
        self.wm.get("buffer").append("hello")
        msgs = cmd(self.router, "/ws")
        text = msgs[0].payload["text"]
        # buffer 有 1 筆
        self.assertIn("1", text)

    def test_ws_switch_valid(self):
        """Test 2a: /ws stt 切換成功"""
        msgs = cmd(self.router, "/ws", ["stt"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("已切換當前工作區至", text)
        self.assertIn("stt", text)
        self.assertEqual(self.wm.current, "stt")

    def test_ws_switch_invalid(self):
        """Test 2b: /ws nope 失敗並回傳可用清單"""
        msgs = cmd(self.router, "/ws", ["nope"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("未知工作區", text)
        self.assertIn("nope", text)
        self.assertIn("buffer", text)
        self.assertIn("stt", text)
        # 當前應不變
        self.assertEqual(self.wm.current, "buffer")


class TestShowCommand(unittest.TestCase):
    """Test 3: /show"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_show_with_content(self):
        """Test 3a: /show 有內容時顯示編號行"""
        self.wm.get("buffer").append("line one")
        self.wm.get("buffer").append("line two")
        msgs = cmd(self.router, "/show")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        # 應包含標頭
        self.assertIn("buffer", text)
        self.assertIn("2", text)
        # 應有編號
        self.assertIn("1", text)
        self.assertIn("line one", text)
        self.assertIn("line two", text)

    def test_show_empty_workspace(self):
        """Test 3b: /show 空工作區顯示空訊息"""
        msgs = cmd(self.router, "/show")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("空的", text)
        self.assertIn("buffer", text)


class TestClearCommand(unittest.TestCase):
    """Test 4: /clear"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clear_current_with_count(self):
        """Test 4a: /clear 清當前工作區並回報原筆數"""
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        msgs = cmd(self.router, "/clear")
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertTrue(ws.is_empty())

    def test_clear_ui_emits_clear_and_status(self):
        """Test 4b: /clear ui 發出 clear 類型事件 + status 待機"""
        msgs = cmd(self.router, "/clear", ["ui"])
        topics = {m.topic: m.payload for m in msgs}
        self.assertIn("ui_event", topics)
        # 應有一個 type=clear 事件
        ui_payloads = [m.payload for m in msgs if m.topic == "ui_event"]
        types = [p.get("type") for p in ui_payloads]
        self.assertIn("clear", types)
        self.assertIn("status", types)
        # status 文字為 "待機"
        status_texts = [p.get("text") for p in ui_payloads if p.get("type") == "status"]
        self.assertIn("待機", status_texts)

    def test_clear_buffer_explicit(self):
        """Test 4c: /clear buffer 清 buffer 工作區"""
        self.wm.get("buffer").append("x")
        msgs = cmd(self.router, "/clear", ["buffer"])
        text = msgs[0].payload["text"]
        self.assertIn("buffer", text)
        self.assertTrue(self.wm.get("buffer").is_empty())

    def test_clear_stt_explicit(self):
        """Test 4d: /clear stt 清 stt 工作區"""
        self.wm.get("stt").append("x")
        msgs = cmd(self.router, "/clear", ["stt"])
        text = msgs[0].payload["text"]
        self.assertIn("stt", text)
        self.assertTrue(self.wm.get("stt").is_empty())

    def test_clear_chat_clears_history_and_reports_count(self):
        """Test 4e: /clear chat 清空 sm history 並回報原筆數"""
        # 種入 3 則歷史
        self.sm.add_message("user", "msg1")
        self.sm.add_message("assistant", "reply1")
        self.sm.add_message("user", "msg2")
        msgs = cmd(self.router, "/clear", ["chat"])
        text = msgs[0].payload["text"]
        self.assertIn("已清空", text)
        self.assertIn("3", text)
        self.assertIn("chat", text)
        # 確認 sm history 已清空
        self.assertEqual(self.sm.message_count(), 0)

    def test_clear_chat_sm_none_friendly_message(self):
        """Test 4f: /clear chat 在 _sm 為 None 時回傳友善訊息，不 AttributeError"""
        router_no_sm, wm_ns, _ = make_router(self._tmp.name, sm=None)
        # 需要手動建一個 session_manager=None 的 router
        from modules.workspace_manager import WorkspaceManager as WM
        wm2 = WM()
        from modules.command_router import CommandRouter as CR
        r2 = CR(workspace_manager=wm2, session_manager=None, export_dir=self._tmp.name)
        payload = {"cmd": "/clear", "args": ["chat"]}
        r2.handle(Message(topic="commands", payload=payload))
        result = []
        while True:
            try:
                result.append(r2.outbox.get_nowait())
            except Exception:
                break
        self.assertEqual(len(result), 1)
        text = result[0].payload["text"]
        # 不應崩潰，應有友善文字
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)


class TestDelCommand(unittest.TestCase):
    """Test 5: /del"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_del_valid_index(self):
        """Test 5a: /del 1 刪除第一筆（1-based）"""
        ws = self.wm.get("buffer")
        ws.append("keep")
        ws.append("delete_me")
        # 切換到 stt 來測試（buffer 預設是當前）
        # 實際上 current=buffer，/del 1 刪除 buffer 第 1 筆（0-indexed 0）
        msgs = cmd(self.router, "/del", ["1"])
        text = msgs[0].payload["text"]
        self.assertIn("1", text)
        self.assertEqual(ws.count(), 1)
        self.assertEqual(ws.lines()[0], "delete_me")  # 原第 2 筆

    def test_del_non_numeric(self):
        """Test 5b: /del abc → 用法訊息"""
        msgs = cmd(self.router, "/del", ["abc"])
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)
        self.assertIn("/del", text)

    def test_del_out_of_range(self):
        """Test 5c: /del 99 → 失敗訊息"""
        ws = self.wm.get("buffer")
        ws.append("only_one")
        msgs = cmd(self.router, "/del", ["99"])
        text = msgs[0].payload["text"]
        self.assertIn("99", text)
        self.assertEqual(ws.count(), 1)  # 未被刪

    def test_del_no_args(self):
        """Test 5d: /del 無參數 → 用法訊息"""
        msgs = cmd(self.router, "/del")
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)


class TestMoveToTopConcatCommands(unittest.TestCase):
    """Test 6: /move /to_top /concat 快樂路徑"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_move_happy_path(self):
        """Test 6a: /move 2 1 移動第 2 筆到第 1 位"""
        ws = self.wm.get("buffer")
        ws.append("first")
        ws.append("second")
        msgs = cmd(self.router, "/move", ["2", "1"])
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertIn("1", text)
        self.assertEqual(ws.lines()[0], "second")

    def test_move_missing_args(self):
        """Test 6b: /move 缺參數 → 用法訊息"""
        msgs = cmd(self.router, "/move", ["1"])
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)

    def test_to_top_happy_path(self):
        """Test 6c: /to_top 不帶參數把最後一筆移到最前"""
        ws = self.wm.get("buffer")
        ws.append("first")
        ws.append("last")
        msgs = cmd(self.router, "/to_top")
        text = msgs[0].payload["text"]
        self.assertIn("最前", text)
        self.assertEqual(ws.lines()[0], "last")

    def test_to_top_with_index(self):
        """Test 6d: /to_top 2 把第 2 筆移到最前"""
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        ws.append("c")
        msgs = cmd(self.router, "/to_top", ["2"])
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertEqual(ws.lines()[0], "b")

    def test_concat_happy_path(self):
        """Test 6e: /concat 壓縮多筆為一筆"""
        ws = self.wm.get("buffer")
        ws.append("hello")
        ws.append("world")
        msgs = cmd(self.router, "/concat")
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertEqual(ws.count(), 1)
        self.assertIn("hello world", ws.lines()[0])


class TestCopyPasteCommands(unittest.TestCase):
    """Test 7-8: /copy /paste"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @mock.patch("utils.clipboard.copy", return_value=(True, ""))
    def test_copy_success(self, mock_copy):
        """Test 7a: /copy 成功複製並回報筆數"""
        ws = self.wm.get("buffer")
        ws.append("line1")
        ws.append("line2")
        msgs = cmd(self.router, "/copy")
        mock_copy.assert_called_once()
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertIn("複製", text)

    def test_copy_empty_workspace(self):
        """Test 7b: /copy 空工作區 → 空的訊息"""
        msgs = cmd(self.router, "/copy")
        text = msgs[0].payload["text"]
        self.assertIn("空的", text)
        self.assertIn("buffer", text)

    @mock.patch("utils.clipboard.copy", return_value=(False, "找不到工具"))
    def test_copy_failure_message(self, mock_copy):
        """Test 7c: /copy 剪貼簿失敗 → 錯誤訊息"""
        self.wm.get("buffer").append("x")
        msgs = cmd(self.router, "/copy")
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)
        self.assertIn("找不到工具", text)

    @mock.patch("utils.clipboard.paste", return_value=(True, "line1\n  \nline2\n"))
    def test_paste_multi_line(self, mock_paste):
        """Test 8: /paste 把多行剪貼簿內容逐非空行 append 到工作區"""
        ws = self.wm.get("buffer")
        msgs = cmd(self.router, "/paste")
        self.assertEqual(ws.count(), 2)
        self.assertEqual(ws.lines(), ["line1", "line2"])
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertIn("貼上", text)

    @mock.patch("utils.clipboard.paste", return_value=(False, "讀取失敗"))
    def test_paste_failure(self, mock_paste):
        """Test 8b: /paste 失敗 → 錯誤訊息，工作區不變"""
        msgs = cmd(self.router, "/paste")
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)
        self.assertTrue(self.wm.get("buffer").is_empty())


class TestExportImportCommands(unittest.TestCase):
    """Test 9: /export + /import 往返"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_then_import_roundtrip(self):
        """Test 9: /export 後 /import 能還原資料"""
        ws = self.wm.get("buffer")
        ws.append("entry_a")
        ws.append("entry_b")
        # 匯出
        export_msgs = cmd(self.router, "/export", ["roundtrip_test"])
        self.assertEqual(len(export_msgs), 1)
        self.assertIn("匯出", export_msgs[0].payload["text"])
        # 清空
        ws.clear()
        self.assertTrue(ws.is_empty())
        # 匯入
        import_msgs = cmd(self.router, "/import", ["roundtrip_test"])
        self.assertEqual(len(import_msgs), 1)
        self.assertIn("匯入", import_msgs[0].payload["text"])
        self.assertIn("2", import_msgs[0].payload["text"])
        self.assertEqual(ws.count(), 2)

    def test_export_no_args_is_error(self):
        """Test 9b: /export 不帶參數應報錯，要求指定檔名"""
        ws = self.wm.get("buffer")
        ws.append("data")
        msgs = cmd(self.router, "/export")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)
        self.assertIn("/export", text)

    def test_import_no_args_is_error(self):
        """Test 9d: /import 不帶參數應報錯"""
        msgs = cmd(self.router, "/import")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)

    def test_import_file_not_found(self):
        """Test 9c: /import 找不到檔案 → 錯誤訊息"""
        msgs = cmd(self.router, "/import", ["nonexistent_xyz"])
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)


class TestSendCommand(unittest.TestCase):
    """Test 10-12: /send"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_send_non_buffer_workspace_rejected(self):
        """Test 10: 當前工作區不是 buffer 時 /send 被拒絕，不發 outbound"""
        self.wm.switch("stt")
        msgs = cmd(self.router, "/send")
        # 只有 ui_event，沒有 outbound
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        text = ui_msgs[0].payload["text"]
        self.assertIn("/send", text)
        self.assertIn("buffer", text)
        self.assertIn("stt", text)

    def test_send_empty_buffer_no_outbound(self):
        """Test 11: buffer 空時 /send 不發 outbound，只發 ui_event 訊息"""
        # buffer is current and empty
        msgs = cmd(self.router, "/send")
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)

    def test_send_with_content_outbound_payload(self):
        """Test 12: buffer 有內容時 /send 發出正確 outbound payload（無 Type 鍵）"""
        ws = self.wm.get("buffer")
        ws.append("hello")
        ws.append("world")
        msgs = cmd(self.router, "/send")

        # 確認有 outbound
        outbound_msgs = [m for m in msgs if m.topic == "outbound"]
        self.assertEqual(len(outbound_msgs), 1)
        payload = outbound_msgs[0].payload

        # 舊版 payload 只有 Title、Content、Metadata.ClientTime，沒有 Type
        self.assertNotIn("Type", payload)
        self.assertIn("hello", payload["Content"])
        self.assertIn("world", payload["Content"])
        self.assertEqual(payload["Title"], self.sm.current_title)
        self.assertIn("ClientTime", payload["Metadata"])
        # ClientTime 應為 ISO 格式 UTC 時間
        ct = payload["Metadata"]["ClientTime"]
        # 能正常解析
        datetime.fromisoformat(ct)

    def test_send_whitespace_only_buffer_no_outbound(self):
        """Test 12e: buffer 僅含空白字元時 /send 不發 outbound，清空 buffer，發 ui 訊息"""
        ws = self.wm.get("buffer")
        ws.append("   ")
        ws.append("  \t  ")
        msgs = cmd(self.router, "/send")
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)
        self.assertTrue(ws.is_empty())

    def test_send_adds_to_session_history(self):
        """Test 12b: /send 把 content 加入 session 歷史"""
        ws = self.wm.get("buffer")
        ws.append("test message")
        cmd(self.router, "/send")
        session = self.sm.get_current_session()
        history = session["history"]
        self.assertTrue(any(h[0] == "user" and "test message" in h[1] for h in history))

    def test_send_clears_buffer(self):
        """Test 12c: /send 後 buffer 應被清空"""
        ws = self.wm.get("buffer")
        ws.append("clear me")
        cmd(self.router, "/send")
        self.assertTrue(ws.is_empty())

    def test_send_emits_sending_and_status_events(self):
        """Test 12d: /send 發出 sending 訊息 + status 傳送中"""
        ws = self.wm.get("buffer")
        ws.append("content")
        msgs = cmd(self.router, "/send")
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        types = [m.payload.get("type") for m in ui_msgs]
        self.assertIn("message", types)
        self.assertIn("status", types)
        # 找 sending 角色的訊息
        sending = [m for m in ui_msgs if m.payload.get("role") == "sending"]
        self.assertTrue(len(sending) >= 1)
        self.assertIn("[傳送內容]", sending[0].payload["text"])
        # status "傳送中"
        status = [m for m in ui_msgs if m.payload.get("type") == "status"]
        self.assertTrue(any("傳送中" in m.payload.get("text", "") for m in status))


class TestQuickSend(unittest.TestCase):
    """Test 13: quick_send 走同一路徑"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_quick_send_empty_buffer_no_outbound(self):
        """Test 13a: QUICK_SEND 在空 buffer 下不發 outbound（與 /send 相同路徑）"""
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = drain(self.router)
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)

    def test_quick_send_with_content_goes_through_send_path(self):
        """Test 13b: QUICK_SEND 有內容時發 outbound（與 /send 相同路徑，無 Type 鍵）"""
        ws = self.wm.get("buffer")
        ws.append("quick content")
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = drain(self.router)
        outbound_msgs = [m for m in msgs if m.topic == "outbound"]
        self.assertEqual(len(outbound_msgs), 1)
        self.assertNotIn("Type", outbound_msgs[0].payload)
        self.assertIn("quick content", outbound_msgs[0].payload["Content"])

    def test_quick_send_non_buffer_workspace_rejected(self):
        """Test 13c: QUICK_SEND 在非 buffer 工作區 → 拒絕，不發 outbound"""
        self.wm.switch("stt")
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = drain(self.router)
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)


class TestWsChatCount(unittest.TestCase):
    """/ws 無參數 — chat 行顯示真實歷史筆數（Task 4 新測試）"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ws_chat_count_zero(self):
        """chat 歷史為空時顯示 0 筆"""
        msgs = cmd(self.router, "/ws")
        text = msgs[0].payload["text"]
        # chat 行應含 '0 筆'
        import re
        chat_line = next(ln for ln in text.splitlines() if "chat" in ln)
        self.assertIn("0", chat_line)

    def test_ws_chat_count_after_add(self):
        """加入 2 則歷史後 /ws 顯示 2 筆"""
        self.sm.add_message("user", "hello")
        self.sm.add_message("assistant", "hi")
        msgs = cmd(self.router, "/ws")
        text = msgs[0].payload["text"]
        chat_line = next(ln for ln in text.splitlines() if "chat" in ln)
        self.assertIn("2", chat_line)

    def test_ws_chat_no_sm_shows_zero_or_omits(self):
        """_sm 為 None 時 /ws chat 行顯示 0 筆（或省略），不崩潰"""
        from modules.workspace_manager import WorkspaceManager as WM
        from modules.command_router import CommandRouter as CR
        wm2 = WM()
        r2 = CR(workspace_manager=wm2, session_manager=None, export_dir=self._tmp.name)
        r2.handle(Message(topic="commands", payload={"cmd": "/ws", "args": []}))
        result = []
        while True:
            try:
                result.append(r2.outbox.get_nowait())
            except Exception:
                break
        self.assertEqual(len(result), 1)
        text = result[0].payload["text"]
        # 至少有 buffer 和 stt，不崩潰
        self.assertIn("buffer", text)


class TestWsChatReadonly(unittest.TestCase):
    """/ws chat 應回唯讀提示，不允許切換"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ws_chat_returns_readonly_message(self):
        """/ws chat 回「chat 為唯讀檢視」提示，current 不變"""
        original_current = self.wm.current
        msgs = cmd(self.router, "/ws", ["chat"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("唯讀", text)
        self.assertIn("chat", text)
        # current 工作區不應變更
        self.assertEqual(self.wm.current, original_current)

    def test_ws_chat_message_mentions_history_and_clear(self):
        """/ws chat 訊息提及 /history 與 /clear chat"""
        msgs = cmd(self.router, "/ws", ["chat"])
        text = msgs[0].payload["text"]
        self.assertIn("/history", text)
        self.assertIn("/clear chat", text)

    def test_ws_chat_not_set_as_current(self):
        """wm.switch('chat') 不應被呼叫 — chat 不可成為當前工作區"""
        # 在切換後 current 仍為 buffer（預設）
        cmd(self.router, "/ws", ["chat"])
        self.assertNotEqual(self.wm.current, "chat")


if __name__ == "__main__":
    unittest.main()
