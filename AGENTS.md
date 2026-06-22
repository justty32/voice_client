# Voice Client — Agent 專案入口

Voice Client 是語音優先的終端／手機 AI 客戶端。桌面主線採 Data Tunnel 架構：
`main.py` → `app.py` 接線，`core/` 負責訊息交換，`modules/` 負責業務流程。

## 先讀哪裡

- 要執行任務：先讀 [WORKFLOWS.md](WORKFLOWS.md)，依使用者意圖選工作流。
- 要理解專案：先讀 [INDEX.md](INDEX.md)，再依 [CODE_MAP](workflows/common/code-map/CODE_MAP.md) 導航。
- 要理解架構：讀 [docs/architecture.md](docs/architecture.md)。

## Always-on 規則

1. 修改前先確認工作樹，保留使用者既有修改，不處理無關變更。
2. 重構必須 behavior-preserving；功能變動要有對應測試。
3. 修改 Python 後至少跑 `.venv/bin/python -m pytest -q`；必要時再做硬體／網路整合測試。
4. 未經使用者要求，不 push、不建立 PR、不擴張成新的功能工作。
5. durable 知識放到所屬工作流或文件層級；本檔只做路由。
6. 尚未完成的跨 session 狀態記到 [SESSION-LOG.md](SESSION-LOG.md)；需要使用者親自驗證的項目記到 [WAIT_USER.md](WAIT_USER.md)。兩者只保留 open 項目。

## 文件分層

`AGENTS.md` → `WORKFLOWS.md` / `INDEX.md` → 工作流入口 → 工作流內容。

結構整理時才讀 [DEV-GUIDE.md](DEV-GUIDE.md)；程式碼慣例與 CODE_MAP 維護規則在
[workflows/common/conventions.md](workflows/common/conventions.md)。
