# feature-dev — 功能開發

## 流程

1. 從 [CODE_MAP](../common/code-map/CODE_MAP.md) 找到領域、協定與現有測試。
2. 以最小增量修改程式碼並補測試。
3. 跑相關測試，再跑完整 `.venv/bin/python -m pytest -q`。
4. 涉及裝置／網路時做可自動化的結構驗證；需真人操作的項目記到
   [WAIT_USER](../../WAIT_USER.md)。
5. 同步 CODE_MAP、架構／使用文件。
6. 使用者要求 commit 時才 commit；push 需另外確認。

跨 session 未完成事項記到 [session-log.md](session-log.md) 與根目錄
[SESSION-LOG](../../SESSION-LOG.md)。
