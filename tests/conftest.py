import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kanzo_check.kanzo import McpStdio, cli, git_repo_with_remote  # noqa: E402

# Kanzo's sync commits with whatever git identity the machine has; give the tests one
os.environ.setdefault("GIT_AUTHOR_NAME", "kanzo-check")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "kanzo-check@example.com")
os.environ.setdefault("GIT_COMMITTER_NAME", "kanzo-check")
os.environ.setdefault("GIT_COMMITTER_EMAIL", "kanzo-check@example.com")

REMOTE = "https://github.com/acme/demo-app.git"


@pytest.fixture
def home(tmp_path) -> Path:
    h = tmp_path / "kanzo-home"
    assert cli("init", home=h).returncode == 0
    return h


@pytest.fixture
def repo(tmp_path) -> Path:
    return git_repo_with_remote(tmp_path / "demo-app", REMOTE)


@pytest.fixture
def agent(home, repo):
    """An agent session started inside the repo, with the project already created."""
    with McpStdio(home, repo) as mcp:
        text, err = mcp.call("create_project", name="Demo App", slug="demo", repo="acme/demo-app")
        assert not err, text
        yield mcp


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout
