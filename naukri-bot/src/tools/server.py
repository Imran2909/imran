"""Local dashboard + bot control server (stdlib only, no new deps).

Run:  python -m src.tools.server      (then open http://127.0.0.1:8765)
Port: env DASHBOARD_PORT, default 8765. Binds 127.0.0.1 (this PC only).

Routes:
  GET  /            -> dashboard shell
  GET  /data.json   -> freshly regenerated bot stats (always current)
  GET  /api/status  -> {"running": bool, "pid": int|null}
  POST /api/start   -> launch `python -m src.orchestrator.run` detached
  POST /api/stop    -> terminate the bot process tree
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PID_FILE = DATA / "bot.pid"
BOT_LOG = DATA / "bot-server.log"
PORT = int(os.getenv("DASHBOARD_PORT", "8765"))


def _alive(pid: int) -> bool:
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            return re.search(rf"\b{pid}\b", out) is not None
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def status() -> dict:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return {"running": False, "pid": None}
    if _alive(pid):
        return {"running": True, "pid": pid}
    try:
        PID_FILE.unlink()
    except Exception:
        pass
    return {"running": False, "pid": None}


def start_bot() -> dict:
    st = status()
    if st["running"]:
        return {"ok": False, "error": "already running", **st}
    DATA.mkdir(parents=True, exist_ok=True)
    log = open(BOT_LOG, "ab")
    kwargs: dict = {"cwd": str(ROOT), "stdout": log, "stderr": subprocess.STDOUT,
                    "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen([sys.executable, "-m", "src.orchestrator.run"], **kwargs)
    PID_FILE.write_text(str(p.pid), encoding="utf-8")
    return {"ok": True, "running": True, "pid": p.pid}


def stop_bot() -> dict:
    st = status()
    if not st["running"]:
        return {"ok": True, "running": False, "pid": None}
    pid = st["pid"]
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=20)
        else:
            os.kill(pid, 15)
    except Exception:
        pass
    import time
    for _ in range(10):
        time.sleep(0.5)
        if not _alive(pid):
            break
    try:
        PID_FILE.unlink()
    except Exception:
        pass
    return {"ok": True, "running": _alive(pid), "pid": pid if _alive(pid) else None}


class Handler(BaseHTTPRequestHandler):
    server_version = "NaukriDash/1.0"

    def _send(self, code: int, body: bytes, ctype: str, nocache=True) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if nocache:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._send(200, (ROOT / "dashboard" / "index.html").read_bytes(), "text/html")
            elif path == "/data.json":
                from src.tools.dashboard import export_dashboard

                data = export_dashboard().read_bytes()
                self._send(200, data, "application/json")
            elif path == "/api/status":
                self._json(status())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/start":
                self._json(start_bot())
            elif path == "/api/stop":
                self._json(stop_bot())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def log_message(self, *args) -> None:
        pass  # quiet; bot logs live in data/


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard: http://127.0.0.1:{PORT}  (Ctrl+C to stop server)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
