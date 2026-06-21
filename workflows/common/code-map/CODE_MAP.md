# CODE_MAP — Voice Client 程式碼導航

修改前從相關領域開始，不必遍讀整個 repo。

## 框架與接線

- `main.py`：桌面薄入口。
- `app.py`：建立 queue、legacy 元件、TunnelModule 與路由接線；統一啟停。
- `core/message.py`：隧道訊息。
- `core/endpoint.py`：Inbox／Outbox。
- `core/exchange.py`：topic 路由與單執行緒交換。
- `core/module.py`：原生業務模組基底。
- `core/adapter.py`：legacy queue 與隧道轉接。
- 測試：`tests/test_core_*`、`tests/test_app_wiring.py`。

## 語音管線

- `record.py`：PyAudio 錄音、音量判定、pre-roll、靜音／時長切片。
- `voice_to_text.py`：faster-whisper STT。
- `text_to_voice.py`：優先級 TTS、播放中斷、平台 driver 與 espeak 語言選擇。
- `modules/stt_gate.py`：辨識文字在 normal／command 模式間分流。
- 測試：`tests/test_record.py`、`test_voice_to_text.py`、`test_stt_gate.py`、
  `test_voice_flow_integration.py`。

## 指令、工作區與對話

- `modules/command_router.py`：熱鍵、斜線指令、語音指令入口與派發。
- `modules/command_handlers/`：CommandRouter 的工作區、對話與語音解析實作。
- `modules/workspace_manager.py`：當前工作區與 raw_text 唯一去向。
- `modules/cli_text_bridge.py`：CLI 文字／EOF 轉隧道訊息。
- `modules/chat_flow.py`：LLM 回覆、歷史、摘要決策、重播與 TTS 派發。
- `workspace.py`：通用工作區資料結構。
- `session_manager.py`：多對話持久化。
- `http_client.py` / `summary_generator.py`：LLM 與摘要 I/O。
- 測試：`tests/test_command_router_*`、`test_workspace*`、`test_chat_flow*`、
  `test_session_manager.py`、`test_cli_text_bridge.py`。

## 介面

- `terminal_input.py`：終端文字與斜線指令來源。
- `keyboard_listener.py`：全域熱鍵來源。
- `tui_renderer.py`：Rich 終端呈現。
- `mobile_server.py`：手機 FastAPI／WebSocket 入口。
- `static/`：手機前端。

## 設定、工具與歷史相容

- `config.py` / `config.ini`：設定讀取與預設值。
- `utils/`：LLM、clipboard、prompt 等共用工具。
- `text_accumulator.py` / `workspace_controller.py`：舊流程相容；桌面新入口已不以其為核心，
  手機路徑仍可能使用，移除前須查引用。
