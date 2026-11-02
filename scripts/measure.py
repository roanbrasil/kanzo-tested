"""Measure the numbers the article quotes, on this machine, and write results/measurements.json.

Article (author's numbers, Apple M4): ~4.1 MB binary, starts in 2 ms, ~4.5 MB RAM idle, 3,000-task board in 17 ms
in the browser, ~900 tokens for the tool list, 10-60 tokens per reply.

    KANZO_BIN=/path/to/kanzo python scripts/measure.py
"""

import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kanzo_check.kanzo import Board, McpStdio, cli, count_tokens, git_repo_with_remote, kanzo_bin, rss_mb  # noqa

N_TASKS = 3000


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def main():
    work = Path(tempfile.mkdtemp(prefix="kanzo-measure-"))
    home = work / "home"
    cli("init", home=home)
    repo = git_repo_with_remote(work / "demo-app", "https://github.com/acme/demo-app.git")
    out = {"kanzo": subprocess.run([kanzo_bin(), "--version"], capture_output=True, text=True).stdout.strip(),
           "machine": f"{platform.system()} {platform.machine()}, {cpu_model()}",
           "binary_mb": round(Path(kanzo_bin()).stat().st_size / 1e6, 2)}

    # start: process launch until the port accepts connections, median of 20 cold launches
    starts = []
    for _ in range(20):
        with Board(home) as b:
            starts.append(b.startup_s * 1000)
    out["startup_ms_median"] = round(statistics.median(starts), 2)

    # agent-facing cost: the tool list + server instructions, sent once per session
    with McpStdio(home, repo) as mcp:
        tools = mcp.tools()
        payload = json.dumps(tools) + mcp.init.get("instructions", "")
        out["tool_list_tokens"], out["tokenizer"] = count_tokens(payload)
        out["tool_count"] = len(tools)

        mcp.call("create_project", name="Demo App", slug="demo", repo="acme/demo-app")
        replies = [mcp.call("create_task", title="Fix login bug", description="Users get a 500 on /login")[0],
                   mcp.call("create_task", title="Write release notes")[0],
                   mcp.call("list_tasks")[0],
                   mcp.call("next_task")[0],
                   mcp.call("add_comment", id="demo#1", body="Null session token; patching.", author="claude")[0],
                   mcp.call("update_task", id="demo#1", status="review")[0],
                   mcp.call("get_task", id="demo#1")[0],
                   mcp.call("list_projects")[0]]
        sizes = [count_tokens(r)[0] for r in replies]
        out["reply_tokens"] = {"min": min(sizes), "max": max(sizes), "each": sizes}

    with Board(home) as b:
        time.sleep(2)
        out["rss_idle_mb"] = round(rss_mb(b.proc.pid), 1)
        for i in range(N_TASKS):
            b.api("POST", "/tasks", {"project": "demo", "title": f"Task {i}"})
        loads = []
        for _ in range(10):
            t0 = time.perf_counter()
            data = b.api("GET", "/board?project=demo")
            loads.append((time.perf_counter() - t0) * 1000)
        assert len(data["tasks"]) >= N_TASKS
        out["board_3000_api_ms_median"] = round(statistics.median(loads), 1)
        out["board_3000_json_kb"] = round(len(json.dumps(data)) / 1e3)
        out["rss_3000_tasks_mb"] = round(rss_mb(b.proc.pid), 1)
        with McpStdio(home, repo) as mcp:
            t0 = time.perf_counter()
            text, _ = mcp.call("list_tasks")
            out["list_tasks_3000"] = {"ms": round((time.perf_counter() - t0) * 1000, 1),
                                      "tokens": count_tokens(text)[0]}

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "measurements.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
