"""mobile/ssl_cert.py — 自簽 SSL 憑證生成（含本機 IP SAN）。"""

import logging
import os

from mobile.net import _get_lan_ip

log = logging.getLogger("mobile_server")


def _ensure_self_signed_cert(cert_path: str, key_path: str) -> bool:
    """生成自簽 SSL 憑證（如果尚未存在）。需要 cryptography 套件。
    憑證包含本機 IP 的 SAN，讓手機瀏覽器可接受（需手動信任一次）。
    """
    if os.path.exists(cert_path) and os.path.exists(key_path):
        log.info("Using existing SSL cert: %s", cert_path)
        return True
    try:
        import datetime
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        log.info("Generating self-signed SSL certificate...")

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # 取得本機 IP，加入 SAN 讓手機可以用 IP 連線
        local_ip = _get_lan_ip()

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "VoiceClient"),
        ])

        san_entries = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
        if local_ip != "127.0.0.1":
            try:
                san_entries.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
            except Exception:
                pass

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
            )
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        os.makedirs(os.path.dirname(cert_path) or ".", exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))
        # 私鑰僅限擁有者讀寫（POSIX）。Windows 上 chmod 幾乎 no-op 但不會壞。
        try:
            os.chmod(key_path, 0o600)
        except OSError as exc:
            log.warning("chmod 600 on %s failed: %s", key_path, exc)
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        log.info("SSL cert generated: %s (valid 10 years, IP: %s)", cert_path, local_ip)
        return True

    except ImportError:
        log.error("SSL cert generation requires the 'cryptography' package: pip install cryptography")
        return False
    except Exception as exc:
        log.error("SSL cert generation failed: %s", exc)
        return False
