# AI 助手專案發展藍圖 (Roadmap)

本文件紀錄了 **Hybrid-Agent-Assist** 專案的未來擴展方向與技術願景。

---

## 1. 輸入介面多樣化 (Universal Input Interfaces)
核心目標：將「向 Session 添加字串」這件事抽象化，使其能從任何來源觸發。

- [ ] **RESTful API Server:** 建立一個輕量級的後端 (如 FastAPI)，允許透過 HTTP POST 請求將字串推送到指定 Session。
- [ ] **多語言 Bindings:** 提供 C++, Node.js, 或 Go 的封裝庫，讓其他程式能輕鬆整合此 AI 助手。
- [ ] **Shell Stdin/Stdout:** 支援 Unix 管道模式，例如 `echo "task" | assistant`。
- [ ] **啟動自動讀取:** 程式啟動時自動讀取特定目錄下的 `.task` 檔案並載入 Session。
- [ ] **WebSocket 雙向通信:** 支援即時的串流輸入與回傳。

---

## 2. 進階沙盒執行環境 (Advanced Sandboxed Execution)
核心目標：讓助手具備執行複雜邏輯（如 Python 腳本）的能力，同時保持絕對安全。

- [ ] **沙盒化 Python 執行:**
    - **受限執行環境:** 研究使用 `RestrictedPython` 或 `Pyodide (WASM)` 限制 Python 能調用的內建模組與函式。
    - **套件白名單:** 限制僅能使用特定版本的科學運算庫 (如 `numpy`, `pandas`)，禁止 `requests`, `socket` 等網路相關套件。
- [ ] **容器化隔離:** 考慮將每個任務的執行環境動態封裝在一個極輕量化的 Docker 容器或 WebAssembly 運行時中。
- [ ] **資源配額管理:** 限制指令執行的最大記憶體、CPU 使用率及執行時間 (TTL)，防止惡意或錯誤的無限迴圈。

---

## 3. 記憶與知識演進
- [ ] **自動化 Context 壓縮:** 當 Session 歷史過長時，自動調用本地模型進行摘要，以節省上下文窗口。
- [ ] **多 Session 關聯分析:** 讓助手具備跨 Session 的知識遷移能力。

---

## 4. 混合模型優化
- [ ] **動態提權模型:** 建立一個評分機制，當本地模型處理失敗率過高時，自動將該類別任務設為「預設調用雲端 API」。
- [ ] **模型快取:** 針對重複性高的指令進行本地快取，降低推理成本。
