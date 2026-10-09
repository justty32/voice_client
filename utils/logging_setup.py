"""utils/logging_setup.py — 桌面（app.py）與手機（mobile_server.py）共用的全域日誌設定。"""

import logging
import os


def setup_logging(config):
    """設定全域日誌：等級與輸出路徑均從 config 讀取。

    原為 app.py 與 mobile_server.py 各自的 `_setup_logging`（內容相同），合併於此。
    """
    level_str = config.get("LOGGING", "level", fallback="INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    log_file = config.get("WORKSPACE", "log_file", fallback="output/system.log")
    # 純檔名（如 system.log）沒有目錄部分，makedirs("") 會拋例外（B13）
    d = os.path.dirname(log_file)
    if d:
        os.makedirs(d, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
