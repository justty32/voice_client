from queue import Empty, Queue

from ui import local_control


def test_local_control_forwards_allowed_command(tmp_path, monkeypatch):
    path = tmp_path / "control.sock"
    monkeypatch.setattr(local_control, "socket_path", lambda: path)
    commands = Queue()
    control = local_control.LocalControl(commands)

    control.start()
    try:
        assert local_control.send_command("RECORD_TOGGLE") == 0
        assert commands.get(timeout=1) == "RECORD_TOGGLE"
    finally:
        control.stop()

    assert not path.exists()


def test_local_control_rejects_unknown_command(tmp_path, monkeypatch):
    monkeypatch.setattr(local_control, "socket_path", lambda: tmp_path / "control.sock")

    assert local_control.send_command("RUN_ARBITRARY_COMMAND") == 2


def test_local_control_ignores_unknown_datagram(tmp_path, monkeypatch):
    import socket

    path = tmp_path / "control.sock"
    monkeypatch.setattr(local_control, "socket_path", lambda: path)
    commands = Queue()
    control = local_control.LocalControl(commands)

    control.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"UNKNOWN", str(path))
        try:
            commands.get(timeout=0.3)
            assert False, "unknown command should not be forwarded"
        except Empty:
            pass
    finally:
        control.stop()


def test_local_control_debounces_duplicate_command(tmp_path, monkeypatch):
    path = tmp_path / "control.sock"
    monkeypatch.setattr(local_control, "socket_path", lambda: path)
    commands = Queue()
    control = local_control.LocalControl(commands)

    control.start()
    try:
        assert local_control.send_command("RECORD_TOGGLE") == 0
        assert local_control.send_command("RECORD_TOGGLE") == 0
        assert commands.get(timeout=1) == "RECORD_TOGGLE"
        try:
            commands.get(timeout=0.3)
            assert False, "duplicate command should be debounced"
        except Empty:
            pass
    finally:
        control.stop()


def test_loop_returns_when_socket_already_closed(tmp_path, monkeypatch):
    # B9：stop() 把 _socket 設為 None 時，_loop 應直接結束而非拋 AssertionError
    monkeypatch.setattr(local_control, "socket_path", lambda: tmp_path / "control.sock")
    control = local_control.LocalControl(Queue())
    control._running = True
    control._socket = None

    control._loop()  # 不得拋例外


def test_main_requires_exactly_one_command(capsys):
    assert local_control.main(["local_control.py"]) == 2
    assert "Usage:" in capsys.readouterr().err


def test_root_shim_runs_from_any_cwd(tmp_path):
    """KDE .desktop 以絕對路徑執行根層 local_control.py；從其他 cwd 也必須能匯入 ui.local_control。"""
    import subprocess
    import sys
    from pathlib import Path

    shim = Path(__file__).resolve().parents[1] / "local_control.py"
    out = subprocess.run([sys.executable, str(shim), "NOT_A_COMMAND"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 2
    assert "Unsupported Voice Client command" in out.stderr
