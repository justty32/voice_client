"""
clipboard.py — 跨平台剪貼簿存取，優雅降級。

優先使用 pyperclip（若已安裝）；否則退回平台原生工具：
  - macOS : pbcopy / pbpaste
  - Windows: clip / powershell Get-Clipboard
  - Linux : wl-copy/wl-paste（Wayland）或 xclip 或 xsel（X11）

都不可用時回傳 (False, 提示訊息)，呼叫端據此提示使用者，而非崩潰。
"""

import logging
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)

_HINT = (
    "找不到可用的剪貼簿工具。"
    "Linux 請安裝 xclip / xsel / wl-clipboard，或 pip install pyperclip；"
    "macOS/Windows 通常內建。"
)


def _pyperclip():
    try:
        import pyperclip
        return pyperclip
    except Exception:
        return None


def _copy_cmd() -> list[str] | None:
    if sys.platform == "darwin":
        return ["pbcopy"]
    if sys.platform == "win32":
        return ["clip"]
    # Linux
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "-b", "-i"]
    return None


def _paste_cmd() -> list[str] | None:
    if sys.platform == "darwin":
        return ["pbpaste"]
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
    # Linux
    if shutil.which("wl-paste"):
        return ["wl-paste", "-n"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard", "-o"]
    if shutil.which("xsel"):
        return ["xsel", "-b", "-o"]
    return None


def available() -> bool:
    return _pyperclip() is not None or _copy_cmd() is not None


def copy(text: str) -> tuple[bool, str]:
    """複製文字到剪貼簿。回傳 (成功, 錯誤訊息)。"""
    pc = _pyperclip()
    if pc is not None:
        try:
            pc.copy(text)
            return True, ""
        except Exception as e:
            log.debug("pyperclip copy failed, fallback to CLI: %s", e)

    cmd = _copy_cmd()
    if cmd is None:
        return False, _HINT
    try:
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)
        return True, ""
    except Exception as e:
        log.error("Clipboard copy failed: %s", e)
        return False, f"剪貼簿複製失敗: {e}"


def paste() -> tuple[bool, str]:
    """從剪貼簿讀取文字。成功回傳 (True, 內容)；失敗回傳 (False, 錯誤訊息)。"""
    pc = _pyperclip()
    if pc is not None:
        try:
            return True, pc.paste()
        except Exception as e:
            log.debug("pyperclip paste failed, fallback to CLI: %s", e)

    cmd = _paste_cmd()
    if cmd is None:
        return False, _HINT
    try:
        out = subprocess.run(cmd, capture_output=True, check=True)
        return True, out.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        log.error("Clipboard paste failed: %s", e)
        return False, f"剪貼簿讀取失敗: {e}"
