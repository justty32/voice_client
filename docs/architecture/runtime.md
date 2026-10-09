# 架構文檔：執行緒模型與錯誤處理

[架構文檔入口](../architecture.md)

## 7. 執行緒模型與錯誤處理

**長駐執行緒**：每個業務模組（錄音、STT、TTS、HTTP…）一條；Exchange 一條；
全部 daemon。`TunnelModule`／`Exchange` 的 `stop()` 會 `join(timeout=2)`；
legacy 模組的 `stop()` 翻旗標後 `join(timeout=1)`（`TerminalInput` 除外：阻塞在 `input()`，
無法喚醒，靠 daemon 隨行程結束）；停機不 drain。

**本機控制**：`LocalControl` 綁定 `$XDG_RUNTIME_DIR/voice-client-control.sock`
（權限 `0600`），只接受固定命令白名單。KDE 快捷鍵啟動短命 helper，透過
Unix datagram 將 `RECORD_TOGGLE` 送入與 `KeyboardListener` 共用的命令 queue。
0.5 秒相同命令去抖用來吸收桌面啟動動作可能產生的重複觸發。

**共享物件**：`Workspace` 與 `SessionManager` 仍被多條執行緒直接呼叫（不走隧道），
兩者以 `threading.RLock` 保護所有公開方法；`/send` 以 `Workspace.drain()` 原子地取出並清空 buffer。
`get_current_session()` 回深複本，內部寫入走私有 `_current()`。sessions 檔先寫
`<檔名>.tmp` 再 `os.replace` 原子寫入；載入時解析失敗會改名備份為 `<檔名>.corrupt-<時間戳>`，
以空集合啟動，不刪任何檔。

**單點交換**：佇列間搬移僅由 Exchange 執行緒進行——資料流可在一處完整記 log。

**啟停**：`app.py:main()` 把所有元件登記進同一個 `Lifecycle`（`app_wiring/assembly.py`），
順序為 9 個 legacy → 5 個原生 → Exchange；`start_all()` 依此順序啟動。關機時先送 `TTS_TERMINATE`，
再 `stop_all()` 以相同正序停止（模組先停、Exchange 最後），個別 `stop()` 例外只記 log、其餘照停。

### 錯誤策略（閉環）

每條失敗路徑都回到上游，UI 不卡在「處理中」也不無聲。

原生模組 `handle()` 例外 → log ＋ `on_handle_error()`；預設發
`[{模組} 錯誤] 處理 {topic} 失敗：{例外文字}` 的 `ui_event`，迴圈續行；子類可覆寫此 hook。

Recorder：開裝置或錄音迴圈例外 → `recorder_event` `error`（CommandRouter 顯示錯誤並回待機），
之後以 `min(2**n, 30)` 秒退避重試（0.1 秒步進，`stop()` 可中斷；成功進入錄音迴圈後 n 歸零）。
STOP 時 `recording_stopped` 帶 `flushed`；`False`（靜音、無音訊送 STT）→ 狀態列直接回「待機」。

STT：模型載入失敗、模型未載入（每段都報）、轉譯例外 → `stt_event` `stt_error`；
空結果 → `stt_empty`；有文字 → 先出 `stt_text` 再 `stt_done`。CommandRouter 收到後狀態列回「待機」
（錄音中途切片的結果不改狀態列，避免蓋掉「錄音中」），錯誤另顯示 `[STT 錯誤] …`。

摘要：例外或空摘要 → `summary_out` `summary_failed`（帶原文）；ChatFlow 顯示
`[摘要失敗] …，改播原文` 並以 medium 播原文。

Kokoro：TTS dispatcher 每輪檢查 worker 存活；死亡 → log error、清當前任務與待播佇列，
自動重啟一次；再死（或重啟失敗）則放棄，之後任務記 warning 丟棄。

Exchange 例外 → log 後續行；無路由訊息 → warning + 丟棄。
