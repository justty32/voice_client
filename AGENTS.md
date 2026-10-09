# Voice Client — Agent 專案入口

Voice Client 是語音優先的終端／手機 AI 客戶端。桌面與手機共用 Data Tunnel 核心：
`main.py` → `app.py`（桌面）與 `mobile_server.py`（手機）都經 `app_wiring/assembly.py` 的
`build_core()` 組裝；`core/` 負責訊息交換，`protocol/` 是 topic／payload／指令集單一來源，
`modules/` 負責業務流程。

## 先讀哪裡

- 要執行任務：先讀 [WORKFLOWS.md](WORKFLOWS.md)，依使用者意圖選工作流。
- 要理解專案：先讀 [INDEX.md](INDEX.md)，再依 [CODE_MAP](workflows/common/code-map/CODE_MAP.md) 導航。
- 要理解架構（資料流、topic、接線）：讀 [docs/architecture.md](docs/architecture.md)。

不要一開始遍讀整個 repo；從 CODE_MAP 的相關領域展開。

## Always-on 規則

1. 修改前先執行 `git status`；工作樹中的既有修改屬於使用者，保留並避開無關變更。
2. 診斷請求只調查與回報，不自動實作修復；變更請求才修改檔案。
3. 重構必須 behavior-preserving；新增功能或修 bug 必須補足相稱測試。
4. 未經使用者要求，不 push、不建立 PR、不擴張成新的功能工作。
5. 使用 `apply_patch` 修改檔案；搜尋優先使用 `rg`／`rg --files`。
6. durable 知識放到所屬工作流或文件層級；本檔只做路由。
7. 尚未完成的跨 session 狀態記到 [SESSION-LOG.md](SESSION-LOG.md)；需要使用者親自驗證的項目記到 [WAIT_USER.md](WAIT_USER.md)。兩者只保留 open 項目。

## 驗證要求

修改 Python 後至少執行 `.venv/bin/python -m pytest -q`；目前完整基準為
`446 passed, 49 subtests passed`。測試層級與硬體驗收規則見 [workflows/testing.md](workflows/testing.md)。
音訊、熱鍵、手機瀏覽器或外部模型的自動測試通過，不等於真人整合驗收完成；
未驗證項記到 WAIT_USER，不可寫成「失敗」或「完成」。

## 維護鏈與專案注意

`程式碼／測試 → CODE_MAP → docs → README`；topic payload 變更要同步生產者、消費者、
接線測試與 `docs/architecture/topics.md`（`tests/test_protocol_contract.py` 會比對）。
指令集變更同步 `docs/user_manual/commands.md`（`tests/test_protocol_commands.py` 會比對）。

- `app.py` 與 `app_wiring/` 保持接線層，不放業務決策；`core/` 不依賴業務模組與 `protocol/`。
- 共享元件（`build_core()`、原生模組、`protocol/`）同時影響桌面與手機兩條入口，修改時兩邊都要檢查。
- Wayland、SSH 或 headless 環境中 `pynput` 全域熱鍵不可用，不代表核心流程壞掉；
  KDE Wayland 另有根層 `local_control.py`（薄 shim → `ui/local_control.py`），見 `docs/kde_wayland_shortcuts.md`。
- TTS driver、voice ID 與音訊裝置依平台不同，測試不可假設所有機器一致。

## 文件分層

`AGENTS.md` → `WORKFLOWS.md` / `INDEX.md` → 工作流入口 → 工作流內容。

結構整理時才讀 [DEV-GUIDE.md](DEV-GUIDE.md) 與 [wf/STRUCTURE.md](wf/STRUCTURE.md)（通用 kernel 補充包見 [wf/README.md](wf/README.md)）；程式碼慣例與 CODE_MAP 維護規則在
[workflows/common/conventions.md](workflows/common/conventions.md)。
