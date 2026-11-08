"""MyLeet local server. Run:  python server.py   then open http://127.0.0.1:8765"""
import json
import mimetypes
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from myleet import core, generator

HOST, PORT = "127.0.0.1", 8765
STATIC = Path(__file__).resolve().parent / "static"
CTYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/api/" in self.path:
            sys.stderr.write("%s\n" % (fmt % args))

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _parts(self):
        return [p for p in self.path.split("?")[0].split("/") if p]

    def do_GET(self):
        parts = self._parts()
        try:
            if parts[:2] == ["api", "problems"]:
                if len(parts) == 2:
                    return self._send(200, core.list_problems())
                return self._send(200, core.load_problem(parts[2]))
            rel = "index.html" if not parts else "/".join(parts[1:]) if parts[0] == "static" else None
            path = (STATIC / rel).resolve() if rel else None
            if path and path.is_file() and STATIC in path.parents:
                ctype = CTYPES.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                if ctype.startswith("text/"):
                    ctype += "; charset=utf-8"
                return self._send(200, path.read_bytes(), ctype)
            self._send(404, {"error": "not found"})
        except (FileNotFoundError, ValueError):
            self._send(404, {"error": "problem not found"})

    def do_POST(self):
        parts = self._parts()
        try:
            body = self._body()
            if parts == ["api", "problems"]:
                slug = generator.generate(body.get("description", ""), body.get("title", ""))
                return self._send(200, {"slug": slug})
            if len(parts) == 4 and parts[:2] == ["api", "problems"]:
                slug, action = parts[2], parts[3]
                if action == "save":
                    core.save_code(slug, body["code"])
                    return self._send(200, {"ok": True})
                if action == "run":
                    scope = "examples" if body.get("scope") == "examples" else "all"
                    return self._send(200, core.run_user_code(slug, body["code"], scope))
            self._send(404, {"error": "not found"})
        except generator.GenerationError as e:
            self._send(400, {"error": str(e)})
        except (FileNotFoundError, ValueError) as e:
            self._send(404, {"error": str(e)})
        except Exception:
            traceback.print_exc()
            self._send(500, {"error": "Internal error, see server console."})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"MyLeet running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
