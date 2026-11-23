# SESSION-LOG — Open 進度

只記錄尚未完成、需要跨 session 延續的工作。完成後移除；結果留在 git log、文件或
[feature-dev/landed](workflows/feature-dev/landed/README.md)。

- [tidy] wf/ 整理成 aos 形式（使用者 2026-11-23：md 不轉 json、拿掉與 aos 重合的、建 index 骨架）：docs 改 md＋各夾 `_index.json`，dev 寫 `wf/tools/index_check_local.py`＋wf-lint 本地 hook；兩座 commit 不 push → 下一步：窗口收兩封 DONE 後驗證（lint --strict、index 檢查、pytest）再 push
- [org] root daemon 的 `AOS_LLM_KERNEL` 是錯路徑（[feedback](wf/aos/feedback.md)），已報 repo-aos `main`，它回 PROGRESS：根因確認，重起整棵樹等使用者決定 → 下一步：收到它的 DONE 後，[wf/aos/README](wf/aos/README.md) 掛載範例拿掉 `AOS_LLM_KERNEL` 那鍵、feedback 那筆註明去向
