voice_client docs 座位的 agent-fsm 定義：格程式動態連結 stock agent-fsm，腦 sol，可開下屬（上限 2）。

# 定義 `docs`

座位的職責、地盤、交接只寫在卡上：[wf/org/docs/README.md](../../../org/docs/README.md)。本夾只放「它是什麼身體」，做法共通的說明見 [wf/aos 入口](../../README.md)。

- **腦**：`llm.json` `{"model": "sol"}`（使用者 2026-11-23：「先都用sol」）。
- **下屬上限**：`subagents.json` `max_subagents` 2（CHOICE 8）。
- **system text**：`system.txt`，以 aos `templates/orgs/basic/extras/system.seat.txt` 為底寫成繁中。
