# Ideas

只放尚未確定要做的想法；一旦確認會做，移到 [roadmap](../roadmap/README.md)。

## Open ideas

- 將 Kokoro ONNX 導入為高品質離線 TTS 後端。
- 讓桌面與手機模式共用同一套 Data Tunnel 業務流程。
- STT 引擎可抽換：`[STT] engine = ...` 設定，`VoiceToText` 以 strategy 切換，對外契約維持
  「WAV → `list[str]` segments → `stt` 工作區」。
- `WorkspaceRegistry`：工作區數量／型別可擴充（`kind`／`policy` 決定可用 CRUD、
  `/ws new|drop` 動態增減），指令層只對 registry 操作，不寫死 stt／buffer／chat。
