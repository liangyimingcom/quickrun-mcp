"""Regression tests for Windows-specific problems (they also run on POSIX).

1. ALLOWED_FOLDERS must split on os.pathsep, keeping drive letters intact.
2. Shell tools must find a bash (Git Bash on Windows) or fall back to cmd.exe.
3. A reply to an abandoned request must never be returned for a later call.
4. A child started without explicit stdio must not hang or inherit the pipes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from quickrun_mcp._proc import IS_WINDOWS, split_paths
from quickrun_mcp.config import Config


def test_allowed_folders_split_on_pathsep(monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("ALLOWED_FOLDERS", f"{a}{os.pathsep}{b}")
    assert Config().allowed_folders == [a, b]


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows drive-letter paths")
def test_windows_drive_letter_not_split(monkeypatch):
    monkeypatch.setenv("ALLOWED_FOLDERS", r"C:\Users\x\data;D:\work")
    assert [str(p) for p in Config().allowed_folders] == [r"C:\Users\x\data", r"D:\work"]
    assert split_paths(r"C:\a;;  ;D:\b ") == [r"C:\a", r"D:\b"]


@pytest.mark.asyncio
async def test_cancelled_call_does_not_leak_reply(basic_worker):
    """Abandon a slow call (as an MCP client does on its own timeout); the next
    call must get its own output, not the late reply of the abandoned one."""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            basic_worker.execute("import time; time.sleep(3); print('FIRST')", timeout=30),
            timeout=0.5,
        )
    await asyncio.sleep(4)  # long enough for the first call to have finished
    result = await basic_worker.execute("print('SECOND')", timeout=10)
    assert "SECOND" in result and "FIRST" not in result


@pytest.mark.asyncio
async def test_timeout_then_reset_does_not_raise(basic_worker):
    r = await basic_worker.execute("import time; time.sleep(30)", timeout=1)
    assert "timeout" in r.lower()
    assert "cleared" in (await basic_worker.reset()).lower()


def _delayed_child_cmd(marker: Path) -> str:
    """Shell command that starts Python ~2s later, i.e. after the worker has
    gone back to waiting for its next request."""
    py = f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').write(\'ok\')"'
    if IS_WINDOWS:
        return f"ping -n 3 127.0.0.1 >nul & {py}"
    return f"sleep 2; {py}"


@pytest.mark.asyncio
async def test_background_child_runs_while_worker_idle(write_worker, workspace):
    marker = workspace / "child_marker.txt"
    code = (
        "import subprocess\n"
        f"subprocess.Popen({_delayed_child_cmd(marker)!r}, shell=True)\n"
        "print('launched')\n"
    )
    assert "launched" in await write_worker.execute(code, timeout=10)
    deadline = time.monotonic() + 15
    while not marker.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.5)  # worker is idle in readline meanwhile
    assert marker.exists(), "child process hung (inherited the worker's stdin pipe?)"


@pytest.mark.asyncio
async def test_child_output_does_not_corrupt_protocol(basic_worker):
    code = (
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-c', 'print(\"CHILD_NOISE\")'])\n"
        "print('PARENT')\n"
    )
    r1 = await basic_worker.execute(code, timeout=20)
    r2 = await basic_worker.execute("print('NEXT')", timeout=10)
    assert "PARENT" in r1
    assert "NEXT" in r2 and "PARENT" not in r2


@pytest.mark.asyncio
async def test_stateless_returns_while_background_child_alive(stateless_ro):
    code = (
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])\n"
        "print('done')\n"
    )
    t0 = time.monotonic()
    r = await stateless_ro.execute(code, timeout=30)
    assert "done" in r
    assert time.monotonic() - t0 < 10, "stateless call waited for a background child"


def test_find_bash_or_cmd_fallback(tmp_path, monkeypatch):
    from quickrun_mcp.shell_tools import find_bash, tool_run_command
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    cfg = Config()
    r = tool_run_command("echo hello", None, 10, cfg, allow_sudo=False, use_sandbox=False)
    if find_bash() is None and not IS_WINDOWS:
        assert r["return_code"] == -1
    else:
        assert r["return_code"] == 0 and "hello" in r["stdout"]


def test_cli_help_and_version_exit_immediately():
    """`quickrun-mcp --help` must print and exit, not start a stdio server."""
    import subprocess
    for flag, needle in (("--help", "usage"), ("--version", "quickrun-mcp")):
        r = subprocess.run(
            [sys.executable, "-c", "import sys; from quickrun_mcp.server import main; sys.argv=['x', %r]; main()" % flag],
            stdin=subprocess.PIPE, capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, r.stderr
        assert needle in r.stdout.lower()
