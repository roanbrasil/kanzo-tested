# Kanzo, tested

Companion code for the article *Your Coding Agents Need a Task Board You Can Actually Watch*. The article is a
walkthrough of [Kanzo](https://github.com/emanuele-em/kanzo), a kanban board and MCP server in one binary. This
repo runs every step of that walkthrough against the real binary and measures the numbers it quotes.

- `tests/`: 21 pytest checks, one file per step of the article. Each one drives a real `kanzo` in a throwaway
  data folder (`--home`), so your own `~/kanzo` is never touched.
- `scripts/measure.py`: binary size, start time, memory, a 3,000-task board, and the token cost seen by an agent.
- `kanzo_check/kanzo.py`: a small standard-library client for the board, its JSON API, the stdio MCP server
  (`kanzo mcp`) and the HTTP MCP endpoint (`/mcp`).

Nothing here installs a service, edits your Claude Code or Codex config, or talks to GitHub. Sync is tested
against a local bare git repo standing in for the private `kanzo-data` repo.

## Run it

```bash
# Kanzo itself: the installer from the article, or a release binary
curl -LsSf https://github.com/emanuele-em/kanzo/releases/latest/download/kanzo-installer.sh | sh

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                       # uses `kanzo` from PATH, or KANZO_BIN=/path/to/kanzo
python scripts/measure.py       # writes results/measurements.json
```

## Measured vs. quoted

Kanzo 0.3.0, Linux x86_64 musl build, Intel i9-11900K (`results/measurements.json`). The article and the Kanzo
README quote the author's numbers from an Apple M4.

| | Quoted | Measured here |
| --- | --- | --- |
| Binary | ~4.1 MB (article), 4.5 MB (Kanzo README) | 4.93 MB |
| Start | 2 ms | 1.6 ms (launch until the port accepts connections, median of 20) |
| Memory, idle | ~4.5 MB | 4.0 MB RSS |
| Memory, 3,000 tasks | 8 MB (Kanzo README) | 4.4 MB RSS |
| 3,000-task board | 17 ms in the browser | 20 ms for the board's JSON API (690 KB); browser rendering not measured |
| Tool list | ~900 tokens, once per session | 912 tokens (10 tools + server instructions) |
| Agent replies | 10 to 60 tokens | 10 to 62 tokens on a small board |

Token counts use tiktoken's `o200k_base` as a stand-in; Claude's and Codex's own tokenizers will differ a little.

One caveat the numbers hide: replies stay small only while the board does. With 3,000 open tasks in one
project, a plain `list_tasks` returns **~34,000 tokens** in one reply, with no paging. Keep `done` work closed
and projects small, or the agent's "cheap" board call eats its context.

## What the walkthrough gets right, step by step

| Step | Checked by | Result |
| --- | --- | --- |
| 1. Install, `--version`, the command list | `test_step1_install.py` | ✅ |
| 2. `kanzo init` makes one folder with `kanzo.db` + `config.toml`; board on localhost only by default | `test_step2_board.py` | ✅ |
| 3. stdio and HTTP MCP; the project comes from the repo's git remote; `link_repo` for multi-repo projects | `test_step3_mcp.py` | ✅ |
| 4. `next_task` moves to `doing`, comments, `review`, `done`; done hidden from agents | `test_step4_workflow.py` | ✅ |
| 4. Backlog is a column agents never take work from | `test_step4_workflow.py` | ✅, but it is off by default |
| 5. Sync through a git repo; both sides changed → you pick one, no merge | `test_step5_sync.py` | ✅ |
| 6. `--home` for separate boards; export to Markdown/JSON, per project, to a file | `test_step2_board.py`, `test_step6_export.py` | ✅ |

`kanzo update`, `kanzo service install` and the network-sharing setup are not exercised: they change the
machine (a systemd user service, the installed binary, an open port).

## Where Kanzo 0.3.0 differs from the article

- **`statuses` in `config.toml` is ignored.** The article's config sets the columns there. In 0.3.0 the key is
  not read (`test_statuses_key_in_config_is_not_read_by_0_3_0`): the columns are always `todo, doing, review,
  done`, plus `backlog` when switched on.
- **Backlog has to be switched on** (Settings → Backlog, i.e. `PATCH /api/settings {"backlog": true}`). Until
  then `create_task(status="backlog")` fails with `unknown status "backlog"`.
- **There is a second human gate: "Human" tasks.** A task with `human: true` stays in `todo` but is hidden from
  `list_tasks` and skipped by `next_task` ("1 human task not shown").
- **Sharing a board on the network has its own commands now.** `kanzo share on` / `kanzo join <ip>` /
  `kanzo leave` replace editing `listen = "0.0.0.0"` by hand. There are still no logins.
- **First sync on the second machine needs `--keep-remote`.** `kanzo sync --repo <url>` on a fresh machine stops
  with "origin/main already holds a board" and exit code 1. Reaching for `--keep-local` there would overwrite
  the shared board with the new machine's empty one.
- **The losing side is backed up.** After `--keep-remote`, this machine's previous board is in `kanzo.db.bak`,
  not only somewhere in git history.
- **`--keep-local` on one machine means a prompt on the others.** If it throws away a commit another machine
  already pushed, that machine's next `kanzo sync` reports a conflict too, which is correct: its board really
  has changes the remote dropped.
- **Not "a handful" of stars.** The repo had 771 GitHub stars when this was written (2 Nov 2026).
