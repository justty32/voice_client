# Voice Client 改進計畫 (2026-04-05)

## 1. Bug 修復清單

- [ ] **SLMProcessor 變數修正**: 在 `__init__` 中將 `model` 賦值給 `self._model`。
- [ ] **SLMProcessor 響應優化**: 將 `_pre_loop` 中的 `get(timeout=0.1)` 改為 `get_nowait()` 並配合微小的 `sleep`，確保指令 (`slm_cmd_queue`) 能被即時處理。
- [ ] **錄音狀態同步**: 
  - `main.py` 的 `is_recording` 應根據 `recorder_event_queue` 的 `recording_started` / `recording_stopped` 更新，而非僅由快捷鍵切換。
  - 這樣能處理 VAD 自動停止錄音的情況。

## 2. 視覺與體驗優化 (TUI)

- [ ] **Live Status Bar**: 使用 `rich.live` 搭配 `Layout` 建立固定的底部狀態面板。
- [ ] **動態波形**: 錄音時在面板顯示 `[ ||||||..... ]` 隨音量變動的條狀圖。
- [ ] **訊息泡泡**: 使用 `Panel` 讓對話訊息更有質感。

## 4. 實施步驟

### 第一階段：基礎修復與同步 (Fixing)
1. 修正 `slm_processor.py` 的變數與迴圈。
2. 修正 `main.py` 的錄音狀態同步邏輯。

### 第二階段：視覺升級 (Visuals)
1. 改進 `tui_renderer.py`，引入 `rich.live`。
2. 在 `record.py` 增加音量數據回傳（透過 `recorder_event_queue`）。


## 額外添加：
添加新快捷鍵：F7，與F8類似，但其錄音出來後的東西經過STT後，會進入指令處理模塊。透過檢測關鍵詞，達到與斜線指令(/new,/send)之類的效果。