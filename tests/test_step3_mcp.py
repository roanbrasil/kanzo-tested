"""Step 3: agents connect over stdio (`kanzo mcp`) or HTTP (`/mcp`) and find the project from the git remote."""

from kanzo_check.kanzo import Board, McpHttp, McpStdio

EXPECTED_TOOLS = {"add_comment", "create_project", "create_task", "delete_task", "get_task", "link_repo",
                  "list_projects", "list_tasks", "next_task", "update_task"}


def test_stdio_lists_the_tools(home, repo):
    with McpStdio(home, repo) as mcp:
        assert mcp.init["serverInfo"]["name"] == "kanzo"
        assert {t["name"] for t in mcp.tools()} == EXPECTED_TOOLS


def test_project_comes_from_the_git_remote(agent):
    text, err = agent.call("list_projects")
    assert "acme/demo-app" in text and "current repo" in text
    text, err = agent.call("create_task", title="no project id in the prompt")
    assert not err and text.startswith("Created demo#1")


def test_unknown_repo_gets_a_helpful_error(home, tmp_path):
    from kanzo_check.kanzo import git_repo_with_remote
    other = git_repo_with_remote(tmp_path / "other", "git@github.com:acme/other.git")
    with McpStdio(home, other) as mcp:
        text, err = mcp.call("list_tasks")
        assert err and 'create_project and repo "acme/other"' in text


def test_link_repo_lets_one_project_span_repos(agent, home, tmp_path):
    from kanzo_check.kanzo import git_repo_with_remote
    agent.call("link_repo", project="demo", repo="acme/demo-frontend")
    agent.call("create_task", title="shared task")
    front = git_repo_with_remote(tmp_path / "front", "https://github.com/acme/demo-frontend")
    with McpStdio(home, front) as mcp:
        text, err = mcp.call("list_tasks")
        assert not err and "shared task" in text


def test_http_mcp_talks_to_the_running_board(home, repo):
    with McpStdio(home, repo) as mcp:
        mcp.call("create_project", name="Demo", slug="demo", repo="acme/demo-app")
        mcp.call("create_task", title="made over stdio")
    with Board(home) as board:
        http = McpHttp(board.url + "/mcp")
        text, err = http.call("list_tasks", project="demo")
        assert not err and "made over stdio" in text
        text, err = http.call("create_task", project="demo", title="made over http")
        assert not err
        assert any(t["title"] == "made over http" for t in _tasks(board))


def _tasks(board):
    return board.api("GET", "/board?project=demo")["tasks"]
