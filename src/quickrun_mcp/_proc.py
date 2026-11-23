"""Cross-platform process helpers (POSIX + Windows)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Iterable

IS_WINDOWS = sys.platform == "win32"


def new_group_kwargs() -> dict:
    """Popen / create_subprocess_exec kwargs that start a new process group."""
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(pid: int) -> None:
    """Kill *pid* and all of its descendants. Never raises.

    POSIX: SIGKILL the process group (the child was started in its own session).
    Windows: ``os.getpgid`` / ``os.killpg`` do not exist there, so use
    ``taskkill /T /F``, which walks the process tree.
    """
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception:
            pass
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def split_paths(raw: str) -> list[str]:
    """Split a PATH-style list: ':' on POSIX, ';' on Windows (os.pathsep)."""
    return [p.strip() for p in raw.split(os.pathsep) if p.strip()]


def join_paths(paths: Iterable[object]) -> str:
    return os.pathsep.join(str(p) for p in paths)
