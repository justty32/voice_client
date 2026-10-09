# WORKFLOWS — 工作流派發器

依使用者意圖選一條工作流，先讀入口檔，再開始工作。

| 使用者意圖 | 工作流 | 入口 |
|---|---|---|
| 開發、修改或修復功能 | feature-dev | [workflows/feature-dev/README.md](workflows/feature-dev/README.md) |
| 重構、拆檔、整理結構 | refactor | [workflows/refactor/README.md](workflows/refactor/README.md) |
| 診斷、可行性研究、技術調查 | investigation | [workflows/investigation/README.md](workflows/investigation/README.md) |
| 把想法討論成設計方案 | spec | [workflows/specs/README.md](workflows/specs/README.md) |
| 把設計展開成可執行計畫 | plan | [plans/README.md](plans/README.md) |
| 記錄未成熟想法 | idea | [workflows/idea/ideas.md](workflows/idea/ideas.md) |
| 記錄確定會做但尚未排程的事 | roadmap | [workflows/roadmap/README.md](workflows/roadmap/README.md) |
| 跑測試、選擇驗證層級 | testing | [workflows/testing.md](workflows/testing.md) |
| 設定開發環境、依賴或外部工具 | dev-env/tooling | [workflows/dev-env.md](workflows/dev-env.md) / [workflows/tooling/README.md](workflows/tooling/README.md) |
| 整體分析外部 repo／系統 | analysis | [wf/workflows/analysis.md](wf/workflows/analysis.md) |
| 為無法直接改的 repo 交付 patch | patch | [wf/workflows/patch.md](wf/workflows/patch.md) |
| 記錄「為什麼選 A 不選 B」 | decisions | [wf/workflows/decisions.md](wf/workflows/decisions.md) |
| 整理文檔結構、搬檔改名 | tidy | [wf/workflows/tidy/README.md](wf/workflows/tidy/README.md) / [moving-things](wf/workflows/refactor/moving-things.md) |

規劃管線：

`idea → roadmap → spec → plan → feature-dev`

跨工作流活狀態：

- 未完成進度：[SESSION-LOG.md](SESSION-LOG.md)
- 需使用者親自操作或驗證：[WAIT_USER.md](WAIT_USER.md)
