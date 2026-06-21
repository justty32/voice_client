"""工作區、剪貼簿、匯入匯出與傳送指令處理。"""

import os
from datetime import datetime, timezone

from utils import clipboard
from workspace import resolve_filename


class WorkspaceCommandMixin:
    """提供 WorkspaceManager 相關指令；由 CommandRouter 組合使用。"""

    @staticmethod
    def _to_int(s) -> int | None:
        try:
            return int(s)
        except (ValueError, TypeError):
            return None

    def _handle_ws(self, args: list) -> None:
        if not args:
            lines = ["工作區列表:"]
            for name in self._wm.names():
                mark = " (當前)" if name == self._wm.current else ""
                ws = self._wm.get(name)
                count = ws.count() if ws is not None else 0
                lines.append(f"  - {name}{mark} · {count} 筆")
            chat_count = self._sm.message_count() if self._sm is not None else 0
            lines.append(f"  - chat · {chat_count} 筆")
            self._ui_msg("\n".join(lines))
            return

        name = args[0].lower()
        if name == "chat":
            self._ui_msg(
                "chat 為唯讀檢視：請用 /history 檢視、/clear chat 清空"
                "（raw_text 不流入 chat）"
            )
            return
        if self._wm.switch(name):
            self._ui_msg(f"已切換當前工作區至: {name}")
        else:
            available = "/".join(self._wm.names())
            self._ui_msg(f"未知工作區: {name}（可用: {available}）")

    def _handle_show(self) -> None:
        name = self._wm.current
        ws = self._wm.get(name)
        if ws is None or ws.is_empty():
            self._ui_msg(f"[{name} 工作區是空的]")
            return
        body = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(ws.lines()))
        self._ui_msg(f"[{name} 工作區 · {ws.count()} 筆]\n{body}")

    def _handle_clear(self, args: list) -> None:
        target = args[0].lower() if args else self._wm.current
        if target == "ui":
            self.emit("ui_event", {"type": "clear"})
            self.emit("ui_event", {"type": "status", "text": "待機"})
            return
        if target == "chat":
            if self._sm is None:
                self._ui_msg("[系統] chat 工作區尚未接入 SessionManager。")
                return
            n = self._sm.clear_history()
            self._ui_msg(f"[系統] chat 工作區（對話歷史）已清空（原含 {n} 筆）。")
            return
        ws = self._wm.get(target)
        if ws is None:
            self._ui_msg(f"未知的清除目標: {target}（可用: ui/buffer/stt/chat）")
            return
        n = ws.clear()
        self._ui_msg(f"[系統] {target} 工作區已清空（原含 {n} 筆）。")

    def _handle_del(self, args: list) -> None:
        if not args:
            self._ui_msg("用法: /del <編號>")
            return
        i = self._to_int(args[0])
        if i is None:
            self._ui_msg("用法: /del <編號>（需為數字）")
            return
        name = self._wm.current
        if self._wm.get(name).delete(i - 1):
            self._ui_msg(f"[系統] 已刪除 {name} 第 {i} 筆。")
        else:
            self._ui_msg(f"[錯誤] {name} 沒有第 {i} 筆。")

    def _handle_move(self, args: list) -> None:
        if len(args) < 2:
            self._ui_msg("用法: /move <來源編號> <目標編號>")
            return
        src, dst = self._to_int(args[0]), self._to_int(args[1])
        if src is None or dst is None:
            self._ui_msg("用法: /move <來源編號> <目標編號>（需為數字）")
            return
        name = self._wm.current
        if self._wm.get(name).move(src - 1, dst - 1):
            self._ui_msg(f"[系統] 已將 {name} 第 {src} 筆移到第 {dst} 位。")
        else:
            self._ui_msg("[錯誤] 移動失敗（編號超出範圍）。")

    def _handle_to_top(self, args: list) -> None:
        idx = self._to_int(args[0]) if args else None
        if args and idx is None:
            self._ui_msg("用法: /to_top [編號]（需為數字）")
            return
        name = self._wm.current
        if not self._wm.get(name).move_to_top((idx - 1) if idx else -1):
            if idx:
                self._ui_msg(f"[錯誤] {name} 沒有第 {idx} 筆，或筆數不足。")
            return
        where = f"第 {idx} 筆" if idx else "最後一筆"
        self._ui_msg(f"[系統] 已將 {name} {where}移至最前方。")

    def _handle_concat(self) -> None:
        name = self._wm.current
        ws = self._wm.get(name)
        if ws.is_empty():
            return
        count = ws.count()
        ws.concat_all(" ")
        self._ui_msg(f"[系統] 已連接 {name} 工作區（將 {count} 筆壓縮為 1 筆）。")

    def _handle_copy(self) -> None:
        name = self._wm.current
        ws = self._wm.get(name)
        if ws.is_empty():
            self._ui_msg(f"[{name} 工作區是空的，沒有可複製的內容]")
            return
        ok, err = clipboard.copy(ws.flatten(seg_sep=" ", entry_sep="\n"))
        self._ui_msg(
            f"[系統] 已複製 {name} 工作區 {ws.count()} 筆到剪貼簿。"
            if ok else f"[錯誤] {err}"
        )

    def _handle_paste(self) -> None:
        ok, data = clipboard.paste()
        if not ok:
            self._ui_msg(f"[錯誤] {data}")
            return
        name = self._wm.current
        ws = self._wm.get(name)
        lines = [ln.strip() for ln in data.splitlines() if ln.strip()]
        for line in lines:
            ws.append(line)
        self._ui_msg(f"[系統] 已從剪貼簿貼上 {len(lines)} 筆到 {name} 工作區。")

    def _handle_export(self, args: list) -> None:
        if not args:
            self._ui_msg("[錯誤] 請指定匯出檔名。例如: /export my_data")
            return
        name = self._wm.current
        path = resolve_filename(" ".join(args), self._export_dir)
        try:
            self._wm.get(name).export(path)
            self._ui_msg(f"[系統] {name} 工作區已匯出至: {path}")
        except Exception as exc:
            self._ui_msg(f"[錯誤] 匯出失敗: {exc}")

    def _handle_import(self, args: list) -> None:
        if not args:
            self._ui_msg("[錯誤] 請指定匯入檔名。")
            return
        name = self._wm.current
        path = resolve_filename(" ".join(args), self._export_dir)
        if not os.path.exists(path):
            self._ui_msg(f"[錯誤] 找不到檔案: {path}")
            return
        try:
            added = self._wm.get(name).import_file(path, append=True)
            self._ui_msg(f"[系統] 已從 {path} 匯入 {added} 筆到 {name} 工作區。")
        except ValueError as exc:
            self._ui_msg(f"[錯誤] {exc}")
        except Exception as exc:
            self._ui_msg(f"[錯誤] 匯入失敗: {exc}")

    def _handle_send(self) -> None:
        current = self._wm.current
        if current != "buffer":
            self._ui_msg(f"[系統] /send 僅適用於 buffer 工作區（當前: {current}）。")
            return
        ws = self._wm.get("buffer")
        if ws.is_empty():
            self._ui_msg("[系統] 緩衝區是空的。")
            return
        content = ws.flatten(seg_sep=" ", entry_sep=" ")
        ws.clear()
        if not content.strip():
            self._ui_msg("[系統] 緩衝區是空的。")
            return
        payload = {
            "Content": content,
            "Title": (self._sm.current_title if self._sm is not None else None) or "default",
            "Metadata": {"ClientTime": datetime.now(timezone.utc).isoformat()},
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
