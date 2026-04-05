import os

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def load_prompt(name: str) -> str:
    """從 prompts/ 目錄載入 {name}.txt 提示詞。找不到時回傳空字串。"""
    path = os.path.normpath(os.path.join(_PROMPTS_DIR, f"{name}.txt"))
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()
