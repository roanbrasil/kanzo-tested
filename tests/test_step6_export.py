"""Step 6: export as Markdown or JSON, whole board or one project."""

import json

from kanzo_check.kanzo import McpStdio, cli


def seed(home, repo):
    with McpStdio(home, repo) as mcp:
        mcp.call("create_project", name="Demo App", slug="demo", repo="acme/demo-app")
        mcp.call("create_project", name="Other", slug="other", repo="acme/other")
        mcp.call("create_task", title="Fix login bug")
        mcp.call("create_task", title="Unrelated", project="other")


def test_markdown_export(home, repo):
    seed(home, repo)
    r = cli("export", home=home)
    assert r.returncode == 0 and "Fix login bug" in r.stdout and "Unrelated" in r.stdout


def test_json_export_is_parseable(home, repo):
    seed(home, repo)
    data = json.loads(cli("export", "-f", "json", home=home).stdout)
    assert "Fix login bug" in json.dumps(data)


def test_one_project_to_a_file(home, repo, tmp_path):
    seed(home, repo)
    out = tmp_path / "board.md"
    assert cli("export", "-p", "demo", "-o", str(out), home=home).returncode == 0
    text = out.read_text()
    assert "Fix login bug" in text and "Unrelated" not in text
