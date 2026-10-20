"""A fake gbd (GrokBotCLI daemon) on a Unix socket, mirroring the real API shapes closely enough
to exercise the bridge: /v1/health, /v1/agents, /v1/send, /v1/ask, /v1/events (SSE)."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import UnixStreamServer
from urllib.parse import parse_qs, urlsplit

BOT = {"id": "agt_1", "name": "Galatiqon · Test", "kind": "bot"}


class FakeGbd:
    """Scripted turn: after a /v1/send, the SSE stream emits `script` events for that bot."""

    def __init__(self, path: str):
        self.path = path
        self.script: list[tuple[str, dict]] = []
        self.sent: list[dict] = []
        self.ask_status = 200
        self.send_status = 200
        self.events_status = 200
        self.events_error = "nope"
        self.event_delay = 0.01
        self.event_queries: list[dict] = []  # the query string of every /v1/events request
        self.closing = False
        self._cond = threading.Condition()
        self._pending: list[list[tuple[str, dict]]] = []
        fake = self

        class Server(UnixStreamServer, ThreadingHTTPServer):
            address_family = socket.AF_UNIX
            allow_reuse_address = True

            def server_bind(self):
                UnixStreamServer.server_bind(self)
                self.server_name, self.server_port = "fake", 0

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json(self, status: int, body) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(n) or b"{}")

            def do_GET(self):
                u = urlsplit(self.path)
                if u.path == "/v1/health":
                    return self._json(200, {"ok": True, "eventsConnected": True, "agents": 1})
                if u.path == "/v1/agents":
                    return self._json(200, [BOT])
                if u.path == "/v1/events":
                    if fake.events_status != 200:
                        return self._json(fake.events_status, {"error": fake.events_error})
                    q = parse_qs(u.query)
                    fake.event_queries.append({k: v[0] for k, v in q.items()})
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(b": hello\n\n")
                    self.wfile.flush()
                    self.close_connection = True  # like gbd: when the stream ends, the connection ends
                    eid = 0
                    while True:
                        with fake._cond:
                            while not fake._pending:
                                fake._cond.wait(timeout=0.2)
                                if fake.closing:
                                    return
                            turn = fake._pending.pop(0)
                        for etype, ev in turn:
                            eid += 1
                            ev = {"id": eid, "type": etype, "agentId": BOT["id"], **ev}
                            if q.get("types") and etype not in q["types"][0].split(","):
                                continue
                            try:
                                self.wfile.write(f"id: {eid}\nevent: {etype}\ndata: {json.dumps(ev)}\n\n".encode())
                                self.wfile.flush()
                            except (BrokenPipeError, ConnectionResetError):
                                return
                            time.sleep(fake.event_delay)
                return self._json(404, {"error": "no route"})

            def do_POST(self):
                u = urlsplit(self.path)
                body = self._body()
                if u.path == "/v1/send":
                    fake.sent.append(body)
                    if fake.send_status != 200:
                        return self._json(fake.send_status, {"error": "no such bot"})
                    ref = body.get("ref", "")
                    turn = [(t, {**ev, "refs": [ref] if ref and "refs" not in ev else ev.get("refs", [])})
                            for t, ev in fake.script]
                    with fake._cond:
                        fake._pending.append(turn)
                        fake._cond.notify_all()
                    return self._json(200, {"delivery": "delivered", "ref": ref})
                if u.path == "/v1/ask":
                    fake.sent.append(body)
                    if fake.ask_status == 504:
                        return self._json(504, {"error": "timed out waiting for the reply", "done": False})
                    if fake.ask_status != 200:
                        return self._json(fake.ask_status, {"error": "no such bot"})
                    msgs = [{"type": t, "agentId": BOT["id"], **ev} for t, ev in fake.script if t == "message"]
                    return self._json(200, {"send": {"delivery": "delivered"}, "messages": msgs,
                                            "reply": "\n\n".join(m["text"] for m in msgs), "done": True})
                return self._json(404, {"error": "no route"})

        self.server = Server(path, Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def push(self, events: list[tuple[str, dict]]) -> None:
        """Emit events that no /v1/send caused: the bot was written to from the app, a routine fired."""
        with self._cond:
            self._pending.append(list(events))
            self._cond.notify_all()

    def start(self) -> "FakeGbd":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.closing = True
        self.server.shutdown()
        self.server.server_close()
        try:
            os.unlink(self.path)
        except OSError:
            pass
