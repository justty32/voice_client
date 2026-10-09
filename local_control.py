"""local_control.py — KDE 全域快捷鍵用的薄 shim。

KDE `.desktop` 以絕對路徑執行
`/home/lorkhan/repo/voice_client/local_control.py RECORD_TOGGLE`；實作在 `ui/local_control.py`。
本檔只把專案根放進 sys.path（讓任意 cwd 都能匯入 `ui`），再轉呼叫 `ui.local_control.main`。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ui.local_control import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
