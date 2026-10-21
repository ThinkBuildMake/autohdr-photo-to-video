import base64
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts import demo_video

SECRET = "correct-horse-battery"


def _clip(path, seconds, audio=True):
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s=320x180:d={seconds}",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=d={seconds}", "-c:a", "aac"]
    subprocess.run([*cmd, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


def test_verify_accepts_picture_and_song(tmp_path, capsys):
    assert demo_video.verify(_clip(tmp_path / "ok.mp4", 3), 2) == 0
    assert "OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    "seconds, audio, message",
    [(3, False, "no song"), (1, True, "only")],
)
def test_verify_rejects(tmp_path, capsys, seconds, audio, message):
    assert demo_video.verify(_clip(tmp_path / "bad.mp4", seconds, audio), 2) == 1
    assert message in capsys.readouterr().err


def test_verify_rejects_missing_file(tmp_path, capsys):
    assert demo_video.verify(str(tmp_path / "nope.mp4"), 2) == 1
    assert "FAIL" in capsys.readouterr().err


def test_fetch_sends_the_passphrase_and_prints_neither_it_nor_the_link(
    tmp_path, capsys, monkeypatch
):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            if self.path.endswith("/video"):
                body = f'{{"downloadUrl": "http://127.0.0.1:{self.server.server_port}/file?sig=SIGNED"}}'
            else:
                body = "video-bytes"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("DEMO_PASSPHRASE", SECRET)
    out = tmp_path / "demo.mp4"
    try:
        code = demo_video.fetch(f"http://127.0.0.1:{server.server_port}", "job-1", str(out))
    finally:
        server.shutdown()

    assert code == 0
    assert out.read_bytes() == b"video-bytes"
    assert seen[0] == "Basic " + base64.b64encode(f"demo:{SECRET}".encode()).decode()
    assert seen[1] is None
    printed = capsys.readouterr()
    assert SECRET not in printed.out + printed.err
    assert "SIGNED" not in printed.out + printed.err


def test_fetch_reports_a_transport_error_and_leaves_no_partial_file(tmp_path, capsys, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.endswith("/video"):
                body = f'{{"downloadUrl": "http://127.0.0.1:{self.server.server_port}/file?sig=SIGNED"}}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body.encode())
            else:
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b"partial")
                self.wfile.flush()
                self.connection.close()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("DEMO_PASSPHRASE", SECRET)
    out = tmp_path / "demo.mp4"
    try:
        code = demo_video.fetch(f"http://127.0.0.1:{server.server_port}", "job-1", str(out))
    finally:
        server.shutdown()

    printed = capsys.readouterr()
    assert code == 1
    assert "fetch failed" in printed.err
    assert not out.exists()
    assert SECRET not in printed.out + printed.err
    assert "SIGNED" not in printed.out + printed.err


def test_fetch_reports_an_unreachable_app(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", SECRET)

    code = demo_video.fetch("http://127.0.0.1:1", "job-1", str(tmp_path / "demo.mp4"))

    printed = capsys.readouterr()
    assert code == 1
    assert "fetch failed" in printed.err
    assert SECRET not in printed.out + printed.err


def test_fetch_keeps_an_existing_output_file_when_it_fails(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", SECRET)
    out = tmp_path / "demo.mp4"
    out.write_bytes(b"old")

    assert demo_video.fetch("http://127.0.0.1:1", "job-1", str(out)) == 1
    assert out.read_bytes() == b"old"


def test_fetch_reports_an_unwritable_output(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", SECRET)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = f'{{"downloadUrl": "http://127.0.0.1:{self.server.server_port}/f"}}'
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode() if self.path.endswith("/video") else b"x")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        code = demo_video.fetch(
            f"http://127.0.0.1:{server.server_port}", "j", str(tmp_path / "no" / "demo.mp4")
        )
    finally:
        server.shutdown()

    assert code == 1
    assert "cannot write" in capsys.readouterr().err
