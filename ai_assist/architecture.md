# AI 助手架構設計書 (Architecture Design)

## 1. 系統願景
建立一個基於 **事件驅動 (Event-Driven)**、具備 **強大沙盒 (Sandbox)** 且可 **無限擴展 (Mod-ready)** 的混合型 AI 助手。系統核心是一個被動的字串列表處理引擎。

---

## 2. 核心驅動：Session 列表管理
- **數據模型：** 每個 Session 是 `List[str]`。
- **並行安全:** 採用 **讀寫鎖 (RWLock)** 機制，支援多讀單寫。
- **觸發機制:** 生產者可選擇是否觸發鏈條，並受反壓機制保護。

---

## 3. Session 持久化 (Persistence & Auto-save) —— **資料安全核心**
為了確保長期運行的穩定性，系統必須具備可靠的磁碟儲存機制。

### 3.1 儲存格式
- **磁碟映射:** 每個 Session 預設映射至沙盒目錄下的特定檔案 (如 `.sessions/{session_id}.json` 或 `.txt`)。
- **結構:** 儲存完整的字串陣列及其時間戳。

### 3.2 自動儲存策略
- **定時儲存 (Periodic Save):** 系統背景執行緒每隔固定時間（如 30 秒或 5 分鐘，可配置）自動將所有變動過的 Session 寫入磁碟。
- **終止保存 (On-exit Save):** 當程式接收到結束訊號 (SIGTERM/SIGINT) 或正常關閉時，強制執行一次全域儲存。
- **手動觸發:** 關鍵鏈條可在執行完畢後手動要求立即持久化。

---

## 4. 鏈條管理與執行規範
### 4.1 鏈條管理器 (Chain Manager)
- **非原子化設計:** 考量實作複雜度與靈活性，鏈條內的操作不要求嚴格原子化。系統改為依賴 **Session 歷史紀錄** 來進行狀態回溯與除錯。
### 4.2 外掛式系統 (Mod System)
- 支援透過 `.py` 檔案動態載入新鏈條。

---

## 5. 並行處理與資源調度 (Concurrency & Scheduling)
### 5.1 執行緒池管理 (Thread Pool Management)
### 5.2 LLM 請求佇列 (LLM Request Queue)

---

## 6. 安全與沙盒機制 (Sandbox)
### 6.1 目錄隔離 (Path Sandboxing)
### 6.2 指令白名單 (Shell Restricted)

---

## 7. 混合推理層 (Hybrid Model Orchestration)
- **本地模型 (Ollama 10B):** "The Sentry"
- **雲端模型 (External API):** "The Expert"

---

## 8. 執行工作流 (Execution Pipeline)
1. **Input:** 向 Session `append` 字串（取得 Write Lock）。
2. **Trigger Decision:** 生產者決定是否觸發。
3. **Request Thread:** 向執行緒池申請資源。
4. **Context Read:** 讀取相關 Session（取得 Read Lock）。
5. **LLM Queue:** 進入請求佇列。
6. **Execution:** 執行邏輯。
7. **Persistence:** 定時或手動將結果同步至磁碟。
