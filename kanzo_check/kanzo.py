"""Small helpers to drive a real Kanzo binary: the board server, the stdio MCP server, the HTTP MCP endpoint,
the board's JSON API and the CLI. Standard library only."""

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def kanzo_bin() -> str:
    path = os.environ.get("KANZO_BIN") or shutil.which("kanzo")
    if not path:
        raise RuntimeError("kanzo not found: install it or set KANZO_BIN=/path/to/kanzo")
    return path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cli(*args: str, home: Path, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([kanzo_bin(), *args, "--home", str(home)], cwd=cwd, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=60)


def rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("no VmRSS")


class Board:
    """`kanzo --no-open --port N` in the background."""

    def __init__(self, home: Path, port: int | None = None):
        self.home, self.port = home, port or free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc = None
        self.startup_s = None

    def __enter__(self):
        t0 = time.perf_counter()
        self.proc = subprocess.Popen([kanzo_bin(), "--home", str(self.home), "--port", str(self.port), "--no-open"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.05):
                    self.startup_s = time.perf_counter() - t0
                    return self
            except OSError:
                time.sleep(0.0005)
        self.proc.kill()
        raise RuntimeError("board did not start")

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(timeout=5)

    def get(self, path: str):
        with urllib.request.urlopen(self.url + path, timeout=10) as r:
            body = r.read()
            return r.status, body

    def api(self, method: str, path: str, body=None):
        req = urllib.request.Request(self.url + "/api" + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return json.loads(raw) if raw else None


class McpStdio:
    """What Claude Code and Codex do with `kanzo mcp`: launch it and speak JSON-RPC over stdio."""

    def __init__(self, home: Path, cwd: Path):
        self.proc = subprocess.Popen([kanzo_bin(), "mcp", "--home", str(home)], cwd=cwd, text=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._id = 0
        self.init = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "kanzo-check", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, **({"params": params} if params else {})})
        resp = json.loads(self.proc.stdout.readline())
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp["result"]

    def tools(self) -> list[dict]:
        return self.request("tools/list")["tools"]

    def call(self, tool: str, **args) -> tuple[str, bool]:
        r = self.request("tools/call", {"name": tool, "arguments": args})
        return r["content"][0]["text"], bool(r.get("isError"))

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class McpHttp:
    """Streamable HTTP MCP at http://localhost:<port>/mcp, for agents that prefer a URL."""

    def __init__(self, url: str):
        self.url, self.session, self._id = url, None, 0
        self.init = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "kanzo-check", "version": "1"}})
        self.notify("notifications/initialized")

    def _post(self, msg):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            self.session = r.headers.get("Mcp-Session-Id", self.session)
            return r.read().decode()

    def notify(self, method):
        self._post({"jsonrpc": "2.0", "method": method})

    def request(self, method, params=None):
        self._id += 1
        raw = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, **({"params": params} if params else {})})
        if raw.lstrip().startswith("{"):
            return json.loads(raw)["result"]
        for line in raw.splitlines():  # server-sent events
            if line.startswith("data:") and line[5:].strip():
                msg = json.loads(line[5:])
                if msg.get("id") == self._id:
                    return msg["result"]
        raise RuntimeError(f"no response in {raw[:200]!r}")

    def call(self, tool: str, **args) -> tuple[str, bool]:
        r = self.request("tools/call", {"name": tool, "arguments": args})
        return r["content"][0]["text"], bool(r.get("isError"))


def git_repo_with_remote(path: Path, remote: str) -> Path:
    """A working copy whose origin points at `remote`: Kanzo finds the project from this, not from the prompt."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
    return path


def count_tokens(text: str) -> tuple[int, str]:
    """Token count with tiktoken's o200k_base when installed (an approximation for any given model's tokenizer),
    otherwise the usual ~4 characters per token."""
    try:
        import tiktoken
        return len(tiktoken.get_encoding("o200k_base").encode(text)), "tiktoken o200k_base"
    except Exception:
        return round(len(text) / 4), "chars/4"
