# investigation — 踩坑

- 「測試通過」不等於音訊硬體、模型檔、系統 driver 與網路服務均可用。
- 文件中的歷史現況可能已過期；涉及 installed package、模型或系統服務時要重新檢查。
- 背景執行緒問題要同時檢查 producer、Exchange route、consumer 與 stop path。
