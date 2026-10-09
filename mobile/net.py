"""mobile/net.py — 本機 LAN IP 偵測。"""

import socket


def _get_lan_ip() -> str:
    """用 UDP socket 取得本機對外 LAN IP（不實際送封包）。
    避開 `gethostbyname(gethostname())` 在 Linux 上被 `/etc/hosts` 的
    `127.0.1.1 hostname` 欺騙成 loopback 的問題。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.5)
        # 8.8.8.8:80 只是路由選擇用的目的，不會真的送封包
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    # fallback
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"
