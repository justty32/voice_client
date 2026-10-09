# WAIT_USER — 等待使用者操作／驗證

只記錄 agent 無法自行完成、需要使用者親自操作的 open 項目，例如麥克風／喇叭實測、
手機連線、外部服務憑證或系統套件安裝。完成後移除。

## Open

- 【未驗證】階段 7b 手機改走 Data Tunnel 後：`python mobile_server.py` 真機連線、錄音上傳（狀態列「處理中」→「待機」）、
  對話往返與朗讀（`tts`）、停止朗讀（`tts_control`）、`/copy`／`/paste` 剪貼簿往返、`/new` 等指令後對話清單更新（`sessions`）、
  停機後 `_buffer_temp.json` 產生；同一手機重新整理或另開分頁時，舊頁面被斷開、新頁面正常收訊（B6）。
- 【未驗證】階段 6 熱鍵派發表改寫後，五個熱鍵訊號（錄音、語音指令、快速送出、停止 TTS、重播原文）
  在 X11（`pynput` F6–F10）與 KDE Wayland（`local_control.py` 快捷鍵）各實測一次仍可用。
- 【未驗證】階段 4 錯誤閉環：靜音錄音後狀態列回「待機」；STT 模型載入失敗時畫面有 `[STT 錯誤]`；拔掉／佔用麥克風後
  Recorder 退避重試恢復；手動殺 Kokoro worker 後 TTS 自動恢復、殺第二次則放棄並寫 log；SLM 關閉時摘要失敗改播原文。
- 【未驗證】階段 5 停機：legacy `stop()` 改 join 後關機無 ALSA 噪音或 traceback（含 LocalControl 不印 AssertionError），
  停機延遲可接受（STT 載入中、TTS 播放中按退出）。
- 【待裁示】D4：`text_accumulator.py`、`workspace_controller.py` 產品碼已零引用並標 DEPRECATED；是否刪除兩檔與其測試
  （預計獨立 commit）。點頭後 [plans/refactor_next/](plans/refactor_next/README.md) 即可封存。
