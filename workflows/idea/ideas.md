# Ideas

只放尚未確定要做的想法；一旦確認會做，移到 [roadmap](../roadmap/README.md)。
括號內為來源：B／P＝2026-07 bug／架構改進健檢報告編號，E§＝擴展方向報告章節（三份皆已封存於 reports/archive/）。

## 架構與健壯性（重構殘留）

- SttGate 在途 STT 的順序競態：audio／stt_text 攜帶錄音當下的模式標記（B11；需產品裁示）。
- Exchange fan-out／unregister／佇列上限與背壓（P4；桌面＋手機同時呈現時再開案）。
- 結構化 `error` topic，Exchange 無路由丟棄計數（P5 殘留）。
- 停機 drain：Exchange 停前清空 outbox、Lifecycle 倒序停機（P6 殘留）。

## 協定與可觀測性（重構殘留）

- Exchange 統計：per-topic 計數、佇列深度、以 `created_at` 量延遲（P10-1）。
- 工作區變更改走 topic request/reply（P2 方案二；鎖已解決正確性）。
- 控制 topic payload 統一為 dict（P3 殘留）；command mixin 依賴以 Protocol 顯式化（P8 殘留）。
- 手機語音指令模式（手機無 F7 等價，B12 殘留）。

## 語音與輸入

- 全系統聽寫：SttGate 加 `dictation` 模式，經 wtype／xdotool 打進聚焦視窗（E§1）。
- 語音指令帶參數：規則式槽位，之後可接 SLM 解析（E§4）。
- 喚醒詞免熱鍵啟動錄音，需與 Recorder 協調麥克風（E§7）。
- STT 引擎可抽換（`[STT] engine`，SenseVoice 已調查），契約維持 WAV → segments（E§6）。

## LLM 與輸出

- LLM 串流回覆＋分句 TTS，降低開口延遲（E§2）。
- `/model` 多組 LLM 設定檔切換（E§3）。
- `/speak` 朗讀剪貼簿；回覆到達時發桌面通知（E§5）。
- 對話長期記憶：本地 embedding 檢索，可先做 `/recall`（E§8）。
- LLM 工具呼叫，先只映射到既有 `commands` 指令集（E§11）。

## 擴充與其他

- 外掛機制：第三方 TunnelModule 自動掛載（E§9）。
- 手機遙控桌面同一會話（E§10；前置 P4 fan-out）。
- `WorkspaceRegistry`：工作區數量／型別可擴充，指令層只對 registry 操作。
- 小項：錄音裝置選擇＋音量表、`/export md`、TTS 合成快取、串流 STT、每日歸檔（E§12）。

## 設定檔整理

- `config.ini` 有鍵沒被讀取（`[SESSION] auto_save`／`backup_interval`、`[WORKSPACE] output_dir`／`permissions_file`、
  `[UI] status_refresh_rate`），`[AUDIO] chunk_duration` 讀了沒用：刪除或接回。
- 程式缺鍵預設與 ini 不一致（`[SLM] enabled`、`[TTS] engine`、`[STT]` 模型／裝置）：統一預設來源。
