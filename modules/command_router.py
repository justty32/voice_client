"""modules.command_router — 指令流唯一消費者。

消費 commands 通道，統一處理熱鍵訊號、終端斜線指令與語音指令。
熱鍵的舊字串訊號（"RECORD_TOGGLE" 等）在 handle() 內正規化為指令 dict，
keyboard_listener.py 毋須修改。

後續任務將在此類擴充工作區指令（Task 3）、對話管理指令（Task 4）
與語音指令解析（Task 5）；dispatch 以明確的 if/elif 分支實作，
保持與既有模組相同的純 Python 風格。
"""

import logging
import os
from datetime import datetime, timezone

from core.message import Message
from core.module import TunnelModule
from utils import clipboard
from workspace import resolve_filename

log = logging.getLogger(__name__)

# 舊熱鍵字串 → 標準化 cmd 名稱
_STR_TO_CMD = {
    "RECORD_TOGGLE": "record_toggle",
    "RECORD_COMMAND_TOGGLE": "record_command_toggle",
    "QUICK_SEND": "quick_send",
    "FORCE_STOP_TTS": "force_stop_tts",
    "PLAY_LAST_ORIGINAL": "play_last",
}


class CommandRouter(TunnelModule):
    """commands 通道的唯一消費者；持有 WorkspaceManager 與 SessionManager 參照。"""

    name = "command_router"
    consumes = ("commands",)

    def __init__(self, workspace_manager, session_manager, export_dir="."):
        super().__init__()
        self._wm = workspace_manager
        self._sm = session_manager          # Task 4 接入，現階段未使用
        self._export_dir = export_dir
        self._is_recording: bool = False

    # ── 公開入口 ──────────────────────────────────────────────────────────

    def handle(self, message: Message) -> None:
        payload = message.payload

        # 第一層：舊字串訊號正規化
        if isinstance(payload, str):
            cmd_name = _STR_TO_CMD.get(payload)
            if cmd_name is None:
                self.emit("ui_event", {
                    "type": "message",
                    "role": "system",
                    "text": f"未知指令: {payload}",
                })
                return
            cmd_item = {"cmd": cmd_name}
        else:
            cmd_item = payload

        self._dispatch(cmd_item)

    # ── 內部派發 ─────────────────────────────────────────────────────────

    def _dispatch(self, cmd_item: dict) -> None:
        """依 cmd_item["cmd"] 路由到對應處理方法。

        後續任務（3-5）在此 if/elif 鏈末、fallthrough 之前插入新分支即可。
        """
        cmd = cmd_item.get("cmd", "")

        if cmd == "record_toggle":
            self._handle_record_toggle(mode="normal", set_mode_on_stop=True)
        elif cmd == "record_command_toggle":
            self._handle_record_toggle(mode="command", set_mode_on_stop=False)
        elif cmd == "quick_send":
            self._handle_send()
        elif cmd == "force_stop_tts":
            self._handle_force_stop_tts()
        elif cmd == "play_last":
            self._handle_play_last()
        # ── 工作區指令（Task 3）──────────────────────────────────────────
        elif cmd == "/ws":
            self._handle_ws(cmd_item.get("args", []))
        elif cmd == "/show":
            self._handle_show()
        elif cmd == "/clear":
            self._handle_clear(cmd_item.get("args", []))
        elif cmd == "/del":
            self._handle_del(cmd_item.get("args", []))
        elif cmd == "/move":
            self._handle_move(cmd_item.get("args", []))
        elif cmd == "/to_top":
            self._handle_to_top(cmd_item.get("args", []))
        elif cmd == "/concat":
            self._handle_concat()
        elif cmd == "/copy":
            self._handle_copy()
        elif cmd == "/paste":
            self._handle_paste()
        elif cmd == "/export":
            self._handle_export(cmd_item.get("args", []))
        elif cmd == "/import":
            self._handle_import(cmd_item.get("args", []))
        elif cmd == "/send":
            self._handle_send()
        # ── 對話管理指令（Task 4）────────────────────────────────────────
        elif cmd in ("/new", "/switch", "/list", "/delete", "/rename",
                     "/history", "/save", "/load") and self._sm is None:
            # 防禦：未接 SessionManager 時給友善訊息而非 AttributeError
            self._ui_msg("[系統] 對話管理功能尚未接入。")
        elif cmd == "/new":
            self._handle_new(cmd_item.get("args", []))
        elif cmd == "/switch":
            self._handle_switch(cmd_item.get("args", []))
        elif cmd == "/list":
            self._handle_list()
        elif cmd == "/delete":
            self._handle_delete(cmd_item.get("args", []))
        elif cmd == "/rename":
            self._handle_rename(cmd_item.get("args", []))
        elif cmd == "/history":
            self._handle_history()
        elif cmd == "/save":
            self._handle_save(cmd_item.get("args", []))
        elif cmd == "/load":
            self._handle_load(cmd_item.get("args", []))
        elif cmd == "/stop":
            self._handle_force_stop_tts()
        elif cmd == "/help":
            self._handle_help()
        elif cmd == "/exit":
            self.emit("app_ctl", "EXIT")
        # ── 語音指令（Task 5）────────────────────────────────────────────
        elif cmd == "voice":
            self._handle_voice(cmd_item.get("args", []))
        elif cmd == "unknown":
            # terminal_input 發 {"cmd":"unknown","args":[原始行]}，顯示 args[0]
            args = cmd_item.get("args", [])
            self._ui_msg(f"未知指令: {args[0] if args else ''}")
        else:
            # 未知指令（Task 4-5 未覆蓋的 cmd 最終落到這裡）
            self.emit("ui_event", {
                "type": "message",
                "role": "system",
                "text": f"未知指令: {cmd}",
            })

    # ── 熱鍵處理（port main.py:120-141）─────────────────────────────────

    def _handle_record_toggle(self, mode: str, set_mode_on_stop: bool) -> None:
        """翻轉錄音狀態；依舊版語意設定 gate_ctl 模式。

        舊 main.py 語意：RECORD_TOGGLE 不論開始/停止一律把 is_command_mode
        清為 False；RECORD_COMMAND_TOGGLE 只在開始時設 True、停止時不變。

        :param mode: 傳給 SttGate 的模式（"normal" 或 "command"）。
        :param set_mode_on_stop: 停止錄音時是否也送 gate_ctl（F8=是、F7=否）。
        """
        self._is_recording = not self._is_recording
        if self._is_recording:
            self.emit("recorder_ctl", "START")
            self.emit("gate_ctl", {"mode": mode})
        else:
            self.emit("recorder_ctl", "STOP")
            if set_mode_on_stop:
                self.emit("gate_ctl", {"mode": mode})

    # ── 工作區指令（Task 3）──────────────────────────────────────────────

    @staticmethod
    def _to_int(s) -> int | None:
        try:
            return int(s)
        except (ValueError, TypeError):
            return None

    def _ui_msg(self, text: str) -> None:
        """便利方法：發 ui_event system 訊息。"""
        self.emit("ui_event", {"type": "message", "role": "system", "text": text})

    def _handle_ws(self, args: list) -> None:
        """無參數 → 列出工作區與筆數；有參數 → 切換當前工作區。"""
        if not args:
            lines = ["工作區列表:"]
            for name in self._wm.names():
                mark = " (當前)" if name == self._wm.current else ""
                ws = self._wm.get(name)
                count = ws.count() if ws is not None else 0
                lines.append(f"  - {name}{mark} · {count} 筆")
            # chat 工作區於階段④接入
            lines.append("  - chat（階段④接入）")
            self._ui_msg("\n".join(lines))
            return

        name = args[0].lower()
        if self._wm.switch(name):
            self._ui_msg(f"已切換當前工作區至: {name}")
        else:
            available = "/".join(self._wm.names())
            self._ui_msg(f"未知工作區: {name}（可用: {available}）")

    def _handle_show(self) -> None:
        """顯示當前工作區內容（帶編號）。"""
        name = self._wm.current
        ws = self._wm.get(name)
        if ws is None or ws.is_empty():
            self._ui_msg(f"[{name} 工作區是空的]")
            return
        body = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(ws.lines()))
        self._ui_msg(f"[{name} 工作區 · {ws.count()} 筆]\n{body}")

    def _handle_clear(self, args: list) -> None:
        """清當前工作區 / 清指定工作區 / 清 ui。"""
        target = args[0].lower() if args else self._wm.current

        if target == "ui":
            self.emit("ui_event", {"type": "clear"})
            self.emit("ui_event", {"type": "status", "text": "待機"})
            return

        if target == "chat":
            self._ui_msg("chat 工作區於階段④接入")
            return

        ws = self._wm.get(target)
        if ws is None:
            self._ui_msg(f"未知的清除目標: {target}（可用: ui/buffer/stt/chat）")
            return

        n = ws.clear()
        self._ui_msg(f"[系統] {target} 工作區已清空（原含 {n} 筆）。")

    def _handle_del(self, args: list) -> None:
        """刪除當前工作區第 i 筆（1-based）。"""
        if not args:
            self._ui_msg("用法: /del <編號>")
            return
        i = self._to_int(args[0])
        if i is None:
            self._ui_msg("用法: /del <編號>（需為數字）")
            return
        name = self._wm.current
        ws = self._wm.get(name)
        ok = ws.delete(i - 1)
        if ok:
            self._ui_msg(f"[系統] 已刪除 {name} 第 {i} 筆。")
        else:
            self._ui_msg(f"[錯誤] {name} 沒有第 {i} 筆。")

    def _handle_move(self, args: list) -> None:
        """移動當前工作區 src → dst（1-based）。"""
        if len(args) < 2:
            self._ui_msg("用法: /move <來源編號> <目標編號>")
            return
        src = self._to_int(args[0])
        dst = self._to_int(args[1])
        if src is None or dst is None:
            self._ui_msg("用法: /move <來源編號> <目標編號>（需為數字）")
            return
        name = self._wm.current
        ws = self._wm.get(name)
        ok = ws.move(src - 1, dst - 1)
        if ok:
            self._ui_msg(f"[系統] 已將 {name} 第 {src} 筆移到第 {dst} 位。")
        else:
            self._ui_msg("[錯誤] 移動失敗（編號超出範圍）。")

    def _handle_to_top(self, args: list) -> None:
        """把指定（或最後一筆）移到最前。"""
        idx = self._to_int(args[0]) if args else None
        if args and idx is None:
            self._ui_msg("用法: /to_top [編號]（需為數字）")
            return
        target0 = (idx - 1) if idx else -1
        name = self._wm.current
        ws = self._wm.get(name)
        ok = ws.move_to_top(target0)
        if not ok:
            if idx:
                self._ui_msg(f"[錯誤] {name} 沒有第 {idx} 筆，或筆數不足。")
            # 筆數不足但未指定 idx → 靜默（與 workspace_controller 一致）
            return
        where = f"第 {idx} 筆" if idx else "最後一筆"
        self._ui_msg(f"[系統] 已將 {name} {where}移至最前方。")

    def _handle_concat(self) -> None:
        """把當前工作區所有 entry 壓縮為一筆。"""
        name = self._wm.current
        ws = self._wm.get(name)
        if ws.is_empty():
            return
        count = ws.count()
        ws.concat_all(" ")
        self._ui_msg(f"[系統] 已連接 {name} 工作區（將 {count} 筆壓縮為 1 筆）。")

    def _handle_copy(self) -> None:
        """複製當前工作區內容到系統剪貼簿。"""
        name = self._wm.current
        ws = self._wm.get(name)
        if ws.is_empty():
            self._ui_msg(f"[{name} 工作區是空的，沒有可複製的內容]")
            return
        text = ws.flatten(seg_sep=" ", entry_sep="\n")
        ok, err = clipboard.copy(text)
        if ok:
            self._ui_msg(f"[系統] 已複製 {name} 工作區 {ws.count()} 筆到剪貼簿。")
        else:
            self._ui_msg(f"[錯誤] {err}")

    def _handle_paste(self) -> None:
        """從剪貼簿貼到當前工作區（每個非空行為一筆）。"""
        ok, data = clipboard.paste()
        if not ok:
            self._ui_msg(f"[錯誤] {data}")
            return
        name = self._wm.current
        ws = self._wm.get(name)
        lines = [ln.strip() for ln in data.splitlines() if ln.strip()]
        for ln in lines:
            ws.append(ln)
        self._ui_msg(f"[系統] 已從剪貼簿貼上 {len(lines)} 筆到 {name} 工作區。")

    def _handle_export(self, args: list) -> None:
        """匯出當前工作區至檔案。"""
        if not args:
            self._ui_msg("[錯誤] 請指定匯出檔名。例如: /export my_data")
            return
        name = self._wm.current
        ws = self._wm.get(name)
        filename = " ".join(args)
        path = resolve_filename(filename, self._export_dir)
        try:
            ws.export(path)
            self._ui_msg(f"[系統] {name} 工作區已匯出至: {path}")
        except Exception as e:
            self._ui_msg(f"[錯誤] 匯出失敗: {e}")

    def _handle_import(self, args: list) -> None:
        """從檔案匯入至當前工作區。"""
        if not args:
            self._ui_msg("[錯誤] 請指定匯入檔名。")
            return
        name = self._wm.current
        ws = self._wm.get(name)
        filename = " ".join(args)
        path = resolve_filename(filename, self._export_dir)
        if not os.path.exists(path):
            self._ui_msg(f"[錯誤] 找不到檔案: {path}")
            return
        try:
            added = ws.import_file(path, append=True)
            self._ui_msg(f"[系統] 已從 {path} 匯入 {added} 筆到 {name} 工作區。")
        except ValueError as e:
            self._ui_msg(f"[錯誤] {e}")
        except Exception as e:
            self._ui_msg(f"[錯誤] 匯入失敗: {e}")

    def _handle_send(self) -> None:
        """傳送 buffer 工作區內容（/send 與 quick_send 共用）。

        Port 自 text_accumulator._flush + main.py 段落 F：
        - 僅 buffer 工作區有效
        - Content = buffer.flatten(seg_sep=" ", entry_sep=" ")
        - payload 含 Content、Title、Metadata.ClientTime（無 Type）
        - add_message("user", content)、emit outbound、emit sending + status
        - 空白內容：清空 buffer 後回傳，不發 outbound
        """
        current = self._wm.current
        if current != "buffer":
            self._ui_msg(f"[系統] /send 僅適用於 buffer 工作區（當前: {current}）。")
            return

        ws = self._wm.get("buffer")
        if ws.is_empty():
            self._ui_msg("[系統] 緩衝區是空的。")
            return

        # 與 text_accumulator._flush 相同的 join 語意：flatten → clear → guard
        content = ws.flatten(seg_sep=" ", entry_sep=" ")
        ws.clear()

        if not content.strip():
            self._ui_msg("[系統] 緩衝區是空的。")
            return

        # 與舊版 payload 結構相同（無 Type 鍵；http_client.py 不讀 Type）
        payload = {
            "Content": content,
            "Title": (self._sm.current_title if self._sm is not None else None) or "default",
            "Metadata": {
                "ClientTime": datetime.now(timezone.utc).isoformat(),
            },
        }

        if self._sm is not None:
            self._sm.add_message("user", content)

        self.emit("ui_event", {
            "type": "message",
            "role": "sending",
            "text": f"[傳送內容] {content}",
        })
        self.emit("outbound", payload)
        self.emit("ui_event", {"type": "status", "text": "傳送中"})

    # ── 語音指令解析（Task 5，port main.py:392-483）──────────────────────────

    def _handle_voice(self, args: list) -> None:
        """語音指令關鍵字解析後內部重派發。

        Port 自 main.py:392-483：
        - 先以原始文字發 [語音指令] 顯示訊息（port main.py:165）
        - 再以 text.lower().strip() 進行關鍵字比對（port main.py:403）
        - 比對順序嚴格遵照 legacy if/elif 梯形順序（不改變優先權）
        - 比對到後內部重派發到 self._dispatch()，不重複實作指令邏輯
        """
        raw_text = args[0] if args else ""

        # 顯示原始（未 lower）辨識文字
        self._ui_msg(f"[語音指令] {raw_text}")

        # 關鍵字比對使用 lowered 文字（port main.py:403）
        text = raw_text.lower().strip()

        # ── 關鍵字梯形（嚴格照 main.py:405-483 順序）────────────────────
        if "new" in text or "新建" in text or "開啟對話" in text:
            # port main.py:407-408: 取第一個詞後面的部分作為 args
            parts = text.split()
            v_args = parts[1:] if len(parts) > 1 else []
            self._dispatch({"cmd": "/new", "args": v_args})

        elif "switch" in text or "切換" in text:
            parts = text.split()
            v_args = parts[1:] if len(parts) > 1 else []
            self._dispatch({"cmd": "/switch", "args": v_args})

        elif "list" in text or "列表" in text or "清單" in text:
            self._dispatch({"cmd": "/list", "args": []})

        elif "delete" in text or "刪除" in text:
            # port main.py:418-422: 尋找關鍵字詞之後的部分
            parts = text.split()
            v_args = []
            for i, p in enumerate(parts):
                if "delete" in p or "刪除" in p:
                    v_args = parts[i + 1:]
                    break
            self._dispatch({"cmd": "/delete", "args": v_args})

        elif "save" in text or "保存" in text or "儲存" in text:
            # port main.py:425-431
            parts = text.split()
            v_args = []
            for i, p in enumerate(parts):
                if "save" in p or "保存" in p or "儲存" in p:
                    v_args = parts[i + 1:]
                    break
            self._dispatch({"cmd": "/save", "args": v_args})

        elif "concat" in text or "壓縮" in text or "連接" in text:
            self._dispatch({"cmd": "/concat", "args": []})

        elif "to top" in text or "置頂" in text or "移至最前" in text:
            self._dispatch({"cmd": "/to_top", "args": []})

        elif "send" in text or "發送" in text or "傳送" in text:
            self._dispatch({"cmd": "/send", "args": []})

        elif "export" in text or "匯出" in text:
            # port main.py:439-446: 尋找關鍵字詞之後的部分
            parts = text.split()
            v_args = []
            for i, p in enumerate(parts):
                if "export" in p or "匯出" in p:
                    v_args = parts[i + 1:]
                    break
            self._dispatch({"cmd": "/export", "args": v_args})

        elif "import" in text or "匯入" in text:
            # port main.py:448-454
            parts = text.split()
            v_args = []
            for i, p in enumerate(parts):
                if "import" in p or "匯入" in p:
                    v_args = parts[i + 1:]
                    break
            self._dispatch({"cmd": "/import", "args": v_args})

        elif "copy" in text or "複製" in text:
            self._dispatch({"cmd": "/copy", "args": []})

        elif "paste" in text or "貼上" in text:
            self._dispatch({"cmd": "/paste", "args": []})

        elif "stop" in text or "停止" in text:
            self._dispatch({"cmd": "/stop", "args": []})

        elif "show" in text or "顯示" in text:
            self._dispatch({"cmd": "/show", "args": []})

        elif "history" in text or "歷史" in text or "紀錄" in text or "記錄" in text:
            self._dispatch({"cmd": "/history", "args": []})

        elif "help" in text or "幫助" in text or "說明" in text or "指令" in text:
            self._dispatch({"cmd": "/help", "args": []})

        elif "工作區" in text or "workspace" in text:
            # port main.py:468-474: 尋找關鍵字詞之後的部分
            parts = text.split()
            v_args = []
            for i, p in enumerate(parts):
                if "工作區" in p or "workspace" in p:
                    v_args = parts[i + 1:]
                    break
            self._dispatch({"cmd": "/ws", "args": v_args})

        elif "clear" in text or "清除" in text:
            # port main.py:476-481: 有三個子分支
            if "buffer" in text or "暫存" in text:
                self._dispatch({"cmd": "/clear", "args": ["buffer"]})
            elif "畫面" in text or "螢幕" in text or "ui" in text or "screen" in text:
                self._dispatch({"cmd": "/clear", "args": ["ui"]})
            else:
                self._dispatch({"cmd": "/clear", "args": []})

        else:
            # port main.py:483: 無法識別
            self._ui_msg(f"無法識別的語音指令: {text}")

    def _handle_force_stop_tts(self) -> None:
        self.emit("tts_ctl", "STOP_SPEECH")
        self.emit("ui_event", {"type": "status", "text": "待機"})

    def _handle_play_last(self) -> None:
        self.emit("ui_event", {
            "type": "message",
            "role": "system",
            "text": "重播功能於階段④接入",
        })

    # ── 對話管理指令（Task 4，port main.py:264-343）──────────────────────

    def _handle_new(self, args: list) -> None:
        """建立新對話；無標題時使用 session_N 格式。"""
        title = " ".join(args) if args else f"session_{len(self._sm.list_sessions()) + 1}"
        self._sm.new_session(title)
        self._ui_msg(f"新建對話: {title}")

    def _handle_switch(self, args: list) -> None:
        """切換對話；無參數預設 default，default 不存在則建立。"""
        title = " ".join(args) if args else "default"
        if self._sm.switch_session(title):
            self._ui_msg(f"切換至: {title}")
        elif not args and title == "default":
            self._sm.new_session("default")
            self._ui_msg("建立並切換至: default")
        else:
            self._ui_msg(f"找不到對話: {title}")

    def _handle_list(self) -> None:
        """列出所有對話並標示當前。"""
        sessions = self._sm.list_sessions()
        current = self._sm.current_title or "無"
        text = "對話列表:\n" + "\n".join(f"  - {s}" for s in sessions)
        text += f"\n\n當前使用session：{current}"
        self._ui_msg(text)

    def _handle_delete(self, args: list) -> None:
        """刪除指定對話。"""
        title = " ".join(args)
        if not title:
            self._ui_msg("用法: /delete [對話名稱]")
            return
        _success, msg = self._sm.delete_session(title)
        self._ui_msg(msg)

    def _handle_rename(self, args: list) -> None:
        """更改對話名稱。"""
        if len(args) < 2:
            self._ui_msg("用法: /rename [舊名稱] [新名稱]")
            return
        old_t, new_t = args[0], args[1]
        _success, msg = self._sm.rename_session(old_t, new_t)
        self._ui_msg(msg)

    def _handle_history(self) -> None:
        """顯示當前對話的歷史紀錄。"""
        history = self._sm.get_history()
        self._ui_msg(history)

    def _handle_save(self, args: list) -> None:
        """將當前對話另存為 JSON 檔案。"""
        filename = " ".join(args) if args else None
        _success, msg = self._sm.save_session_to_file(filename)
        self._ui_msg(msg)

    def _handle_load(self, args: list) -> None:
        """從 JSON 檔案載入對話。"""
        if not args:
            self._ui_msg("用法: /load [檔名]")
            return
        filename = " ".join(args)
        _success, msg = self._sm.load_session_from_file(filename)
        self._ui_msg(msg)

    def _handle_help(self) -> None:
        """顯示所有可用指令說明（port main.py:340）。"""
        help_text = (
            "/new [title]  /switch [title]  /list  /delete [title]  /save [file]  "
            "/load [file]  /rename [old] [new]  /history  /ws [name]  /show  "
            "/clear [ui|stt|buffer|chat]  /copy  /paste  /del <i>  /move <i> <j>  "
            "/to_top [i]  /concat  /send  /export  /import  /stop  /help  /exit"
        )
        self._ui_msg(help_text)
