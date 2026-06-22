# Voice Client — Claude Code 專案入口

Voice Client 是語音優先的終端／手機 AI 客戶端。桌面主線採 Data Tunnel 架構：
`main.py` → `app.py` 接線，`core/` 負責訊息交換，`modules/` 負責業務流程。

本檔是 Claude Code 的完整頂層指令，不假設 Claude 會另外讀取 `AGENTS.md`。

## 每個任務的起點

1. 先讀 [WORKFLOWS.md](WORKFLOWS.md)，依使用者意圖選擇工作流。
2. 讀該工作流入口，再開始調查或修改。
3. 需要程式碼導航時讀 [INDEX.md](INDEX.md) 與
   [CODE_MAP](workflows/common/code-map/CODE_MAP.md)。
4. 涉及資料流、topic 或接線時讀 [docs/architecture.md](docs/architecture.md)。

不要一開始遍讀整個 repo；從 CODE_MAP 的相關領域展開。

## Always-on 規則

1. 修改前先執行 `git status`。工作樹中的既有修改屬於使用者，保留並避開無關變更。
2. 診斷請求只調查與回報，不自動實作修復；變更請求才修改檔案。
3. 重構必須 behavior-preserving，不得趁重構加入未要求的新行為。
4. 未經使用者要求，不 push、不建立 PR、不開始範圍外的新工作。
5. 使用 `apply_patch` 修改檔案；搜尋優先使用 `rg`／`rg --files`。
6. 新增功能或修 bug 必須補足相稱測試；不能只靠手動閱讀判定完成。
7. durable 知識放到所屬工作流或文件層級，不把所有細節堆回本檔。

## 驗證要求

修改 Python 後至少執行：

```bash
.venv/bin/python -m pytest -q
```

目前完整基準為 `339 passed, 5 subtests passed`。需要時再執行：

```bash
.venv/bin/python -m unittest discover -s tests
python -m compileall -q -x '/(\.venv|\.git)/' .
```

測試層級與硬體驗收規則見 [workflows/testing.md](workflows/testing.md)。
系統 Python 可能沒有 `pytest`，優先使用專案 `.venv`。

音訊、熱鍵、手機瀏覽器或外部模型的自動測試通過，不等於真人整合驗收完成。
需要使用者親自操作的項目記到 [WAIT_USER.md](WAIT_USER.md)，不可把「未驗證」寫成「失敗」或「完成」。

## 程式碼與文件維護鏈

`程式碼／測試 → CODE_MAP → docs → README`

- `app.py` 保持接線層，不放業務決策。
- `core/` 不依賴 Voice Client 業務模組。
- topic payload 是模組間協定；變更時同步生產者、消費者、接線測試與架構文件。
- 新增、刪除檔案或顯著改變職責時，更新 CODE_MAP。
- 改資料流、topic、啟停順序時，更新 `docs/architecture.md`。
- 改使用者指令、設定或操作時，更新 `docs/user_manual.md` 與必要的 README。
- 新增依賴時，更新 `requirements.txt` 與 [tooling](workflows/tooling/README.md)。
- CODE_MAP 與程式碼衝突時，以程式碼為準並立即修正 CODE_MAP。

完整慣例見 [workflows/common/conventions.md](workflows/common/conventions.md)。

## 專案特別注意

- 桌面入口已使用 Data Tunnel；`mobile_server.py` 尚未完全對齊，修改共享元件時要檢查兩條入口。
- `text_accumulator.py`、`workspace_controller.py` 是歷史相容路徑，移除前必須先查引用。
- Wayland、SSH 或 headless 環境中 `pynput` 全域熱鍵不可用，不代表核心流程壞掉；
  KDE Wayland 另有 `local_control.py` 路徑，詳見 `docs/kde_wayland_shortcuts.md`。
- TTS driver、voice ID 與音訊裝置依平台不同，測試不可假設所有機器一致。

## 規劃與狀態

規劃管線：

`idea → roadmap → spec → plan → feature-dev`

- 工作流派發：[WORKFLOWS.md](WORKFLOWS.md)
- 專案地圖：[INDEX.md](INDEX.md)
- 未完成的跨 session 進度：[SESSION-LOG.md](SESSION-LOG.md)
- 等待使用者操作／驗證：[WAIT_USER.md](WAIT_USER.md)

`SESSION-LOG.md` 與 `WAIT_USER.md` 只保留 open 項目；完成後移除。已落地結果放到文件、
[feature-dev/landed](workflows/feature-dev/landed/README.md) 或 git 歷史。

結構整理時才讀 [DEV-GUIDE.md](DEV-GUIDE.md)，不要把它當成每個任務的固定程序。
