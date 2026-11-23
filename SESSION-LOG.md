# SESSION-LOG — Open 進度

只記錄尚未完成、需要跨 session 延續的工作。完成後移除；結果留在 git log、文件或
[feature-dev/landed](workflows/feature-dev/landed/README.md)。

- [org] root daemon 的 `AOS_LLM_KERNEL` 是錯路徑（[feedback](wf/aos/feedback.md)），已報 repo-aos `main`，它回 PROGRESS：根因確認，重起整棵樹等使用者決定 → 下一步：收到它的 DONE 後，[wf/aos/README](wf/aos/README.md) 掛載範例拿掉 `AOS_LLM_KERNEL` 那鍵、feedback 那筆註明去向
