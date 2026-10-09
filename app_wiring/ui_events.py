"""app_wiring/ui_events.py — Exchange 內 ui_event dict → TuiRenderer UiEvent 的轉換。"""

# tui_renderer 依賴 rich，採延遲匯入。
# _dict_to_ui_event 使用 _make_ui_event() 工廠以保持可測試性：
# 成功時回傳真實 UiEvent（供 TuiRenderer 使用），
# 失敗時（rich 未安裝）回傳等效的 _UiEventClass 替代類（屬性相容）。
try:
    from tui_renderer import UiEvent as _UiEventClass
except ImportError:  # pragma: no cover
    from dataclasses import dataclass as _dataclass, field as _field
    from typing import Any as _Any

    @_dataclass
    class _UiEventClass:  # type: ignore[no-redef]
        """rich 未安裝時的輕量替代（屬性與 UiEvent 相容）。"""
        event_type: str
        data: _Any = _field(default=None)


def _dict_to_ui_event(payload: dict):
    """將 Exchange 內流通的 ui_event dict 轉換為 TuiRenderer 需要的 UiEvent 物件。

    支援三種形狀：
    - {"type":"status","text":str}   → UiEvent("status", text)
    - {"type":"message","role":str,"text":str}
                                     → UiEvent("message", {"role":..., "text":...})
    - {"type":"clear"}               → UiEvent("clear", None)

    未知 type → 安全 fallback：UiEvent("message", {"role":"system","text":str(payload)})

    使用模組頂層的 _UiEventClass（rich 可用時為真實 UiEvent，否則為相容替代），
    確保此函式在測試環境中不依賴 rich 亦可呼叫。
    """
    kind = payload.get("type", "")

    if kind == "status":
        return _UiEventClass("status", payload.get("text", ""))

    if kind == "message":
        return _UiEventClass("message", {
            "role": payload.get("role", "system"),
            "text": payload.get("text", ""),
        })

    if kind == "clear":
        return _UiEventClass("clear", None)

    # 未知型別 → 安全 fallback，以 system 訊息顯示原始 payload
    return _UiEventClass("message", {"role": "system", "text": str(payload)})
