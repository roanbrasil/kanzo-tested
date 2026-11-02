"""Step 4: the daily loop, the human gate (Backlog column and Human tasks)."""

from kanzo_check.kanzo import Board, McpStdio


def test_take_next_task_comment_review_done(agent):
    agent.call("create_task", title="Fix login bug", description="Users get 500 on /login")
    agent.call("create_task", title="Write docs")

    text, err = agent.call("next_task")  # "take the next task from kanzo and do it"
    assert not err and text.startswith("Moved to doing:") and "demo#1 Fix login bug" in text

    agent.call("add_comment", id="demo#1", body="Found it: null session token", author="claude")
    text, _ = agent.call("update_task", id="demo#1", status="review")
    assert "doing -> review" in text

    text, _ = agent.call("get_task", id="demo#1")
    assert "status: review" in text and "claude" in text and "null session token" in text

    text, _ = agent.call("update_task", id="demo#1", status="done")
    assert "review -> done" in text
    text, _ = agent.call("list_tasks")
    assert "Fix login bug" not in text  # done is left out by default


def test_human_tasks_are_hidden_from_agents(agent):
    agent.call("create_task", title="Pick a logo", human=True)
    text, _ = agent.call("list_tasks")
    assert "Pick a logo" not in text and "1 human task not shown" in text
    text, _ = agent.call("next_task")
    assert text.startswith("Nothing in todo")


def test_backlog_is_off_by_default_and_agents_skip_it_when_on(home, repo):
    with McpStdio(home, repo) as mcp:
        mcp.call("create_project", name="Demo", slug="demo", repo="acme/demo-app")
        text, err = mcp.call("create_task", title="half-baked idea", status="backlog")
        assert err  # no Backlog column until it is switched on

    with Board(home) as board:
        board.api("PATCH", "/settings", {"backlog": True})  # Settings -> Backlog in the UI
        assert board.api("GET", "/board?project=demo")["statuses"][0] == "backlog"
        idea = board.api("POST", "/tasks", {"project": "demo", "title": "half-baked idea"})
        board.api("POST", f"/tasks/{idea['id']}/move", {"status": "backlog"})

        with McpStdio(home, repo) as mcp:
            text, _ = mcp.call("next_task")
            assert text.startswith("Nothing in todo")  # the agent does not touch the backlog

        board.api("POST", f"/tasks/{idea['id']}/move", {"status": "todo"})  # you authorise it
        with McpStdio(home, repo) as mcp:
            text, _ = mcp.call("next_task")
            assert "half-baked idea" in text
