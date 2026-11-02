"""Step 5: sync through a git repo you own. A local bare repo stands in for the private GitHub repo."""

import subprocess

import pytest

from kanzo_check.kanzo import McpStdio, cli


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "kanzo-data.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path


def tasks(home, repo):
    with McpStdio(home, repo) as mcp:
        return mcp.call("list_tasks")[0]


def add(home, repo, title, create_project=False):
    with McpStdio(home, repo) as mcp:
        if create_project:
            mcp.call("create_project", name="Demo", slug="demo", repo="acme/demo-app")
        mcp.call("create_task", title=title)


def test_two_machines_share_one_board(tmp_path, remote, repo):
    laptop, desktop = tmp_path / "laptop", tmp_path / "desktop"
    add(laptop, repo, "written on the laptop", create_project=True)

    r = cli("sync", "--repo", str(remote), home=laptop)
    assert r.returncode == 0 and "for the first time" in r.stdout
    assert (laptop / ".git").is_dir()  # the data folder became a git repo

    # second machine: the repo already holds a board, so Kanzo asks which side to keep
    r = cli("sync", "--repo", str(remote), home=desktop)
    assert r.returncode == 1 and "--keep-remote" in r.stderr + r.stdout
    assert cli("sync", "--keep-remote", home=desktop).returncode == 0
    assert "written on the laptop" in tasks(desktop, repo)

    # the routine: sync when you leave, sync when you arrive
    add(desktop, repo, "written on the desktop")
    assert cli("sync", home=desktop).returncode == 0
    assert cli("sync", home=laptop).returncode == 0
    assert "written on the desktop" in tasks(laptop, repo)


def test_both_changed_means_you_pick_a_side_and_nothing_is_merged(tmp_path, remote, repo):
    a, b = tmp_path / "a", tmp_path / "b"
    add(a, repo, "base", create_project=True)
    cli("sync", "--repo", str(remote), home=a)
    cli("sync", "--repo", str(remote), home=b)
    cli("sync", "--keep-remote", home=b)

    add(a, repo, "only on A")
    add(b, repo, "only on B")
    assert cli("sync", home=a).returncode == 0
    r = cli("sync", home=b)
    assert r.returncode == 1 and "can't be merged" in r.stderr + r.stdout

    assert cli("sync", "--keep-remote", home=b).returncode == 0
    board_b = tasks(b, repo)
    assert "only on A" in board_b and "only on B" not in board_b
    assert (b / "kanzo.db.bak").exists()  # the losing side is kept next to the board, not lost


def test_keep_local_overwrites_the_remote(tmp_path, remote, repo):
    a, b = tmp_path / "a", tmp_path / "b"
    add(a, repo, "base", create_project=True)
    cli("sync", "--repo", str(remote), home=a)
    cli("sync", "--repo", str(remote), home=b)
    cli("sync", "--keep-remote", home=b)
    add(a, repo, "only on A")
    add(b, repo, "only on B")
    cli("sync", home=a)
    assert cli("sync", "--keep-local", home=b).returncode == 0
    # A's pushed commit was just thrown away by B, so A's history diverged: it is asked to pick a side too
    assert cli("sync", home=a).returncode == 1
    assert cli("sync", "--keep-remote", home=a).returncode == 0
    board_a = tasks(a, repo)
    assert "only on B" in board_a and "only on A" not in board_a
