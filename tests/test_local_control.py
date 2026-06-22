from queue import Empty, Queue

import local_control


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
