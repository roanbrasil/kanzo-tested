"""Step 2 and Step 6: the data folder, the config file, the board in the browser."""

import tomllib

from kanzo_check.kanzo import Board, cli


def test_init_creates_one_folder_with_db_and_config(home):
    assert (home / "kanzo.db").exists()
    cfg = tomllib.loads((home / "config.toml").read_text())
    assert cfg["port"] == 4242
    assert cfg["listen"] == "127.0.0.1"  # local only by default; there are no logins
    assert cfg["mcp_http"] is True


def test_board_serves_the_web_app(home):
    with Board(home) as board:
        status, body = board.get("/")
        assert status == 200 and b"/app.js" in body
        assert board.startup_s < 1


def test_statuses_key_in_config_is_not_read_by_0_3_0(home, repo):
    """The article's config shows `statuses = [...]`; 0.3.0 ignores it and keeps the four default columns."""
    from kanzo_check.kanzo import McpStdio
    with (home / "config.toml").open("a") as f:
        f.write('\nstatuses = ["todo", "doing", "qa", "review", "done"]\n')
    with McpStdio(home, repo) as mcp:
        mcp.call("create_project", name="Demo", slug="demo", repo="acme/demo-app")
        text, err = mcp.call("create_task", title="x", status="qa")
        assert err and "use one of: todo, doing, review, done" in text


def test_home_flag_keeps_boards_apart(tmp_path):
    a, b = tmp_path / "client-a", tmp_path / "client-b"
    assert cli("init", home=a).returncode == 0 and cli("init", home=b).returncode == 0
    assert (a / "kanzo.db").exists() and (b / "kanzo.db").exists()
