"""Step 1: the binary is on PATH (or KANZO_BIN) and is small."""

from pathlib import Path

from kanzo_check.kanzo import kanzo_bin
import subprocess


def test_version():
    out = subprocess.run([kanzo_bin(), "--version"], capture_output=True, text=True).stdout
    assert out.startswith("kanzo ")


def test_single_small_binary():
    size_mb = Path(kanzo_bin()).stat().st_size / 1e6
    assert size_mb < 6  # article: ~4.1 MB on macOS; the Linux x86_64 musl build of 0.3.0 is 4.9 MB


def test_every_command_in_the_quick_reference_exists():
    help_text = subprocess.run([kanzo_bin(), "--help"], capture_output=True, text=True).stdout
    for cmd in ["mcp", "init", "sync", "export", "update", "service"]:
        assert f"  {cmd} " in help_text
