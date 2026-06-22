# refactor — 重構整理

重構預設 behavior-preserving。

1. 一次只整理一個面向：程式碼、CODE_MAP、文件或範例。
2. 程式碼重構完成後立即同步 CODE_MAP。
3. 跑相關與完整測試，確認公開行為不變。
4. 若工作跨 session，記到 [session-log.md](session-log.md)。
5. 拆分原則見 [DEV-GUIDE](../../DEV-GUIDE.md)。
