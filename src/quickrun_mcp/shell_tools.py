"""
Shell execution tools: run_command, run_script, list_processes.

Design goals (vs common shell-runner MCP reference implementation):
  - Same tool names and return format for drop-in compatibility.
  - Adds: truncated, duration_ms fields.
  - Fixes: proper killpg on timeout (reference silently orphans child processes).
  - Adds: extended DANGEROUS_PATTERNS; sudo blocked by default (SHELL_ALLOW_SUDO=true).
  - Adds: optional SHELL_SANDBOX=true reuses sandbox-exec profile from sandbox.py.
  - shell=True is intentionally NOT used; bash -c is used instead (safer arg handling).
  - Windows: bash is looked up in Git for Windows (or QUICKRUN_BASH); run_command
    falls back to cmd.exe when no bash is found; list_processes uses tasklist.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from ._proc import IS_WINDOWS, kill_tree, new_group_kwargs
from .config import Config

# ---------------------------------------------------------------------------
# Dangerous-command patterns
# Format: (regex, human description)
# ---------------------------------------------------------------------------

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Filesystem nukes
    (r"rm\s+-[rRfF]*[rR][rRfF]*\s+/(?:\s|$)", "rm -rf /"),
    (r"rm\s+-[rRfF]*[rR][rRfF]*\s+/\*", "rm -rf /*"),
    (r"rm\s+-[rRfF]*[rR][rRfF]*\s+~(?:/|\s|$)", "rm -rf ~"),
    (r"rm\s+-[rRfF]*[rR][rRfF]*\s+\$HOME(?:/|\s|$)", "rm -rf $HOME"),
    # Disk operations
    (r"\bmkfs\b", "filesystem format (mkfs)"),
    (r"\bdd\b.*\bof=/dev/[sh]d", "dd write to block device"),
    (r">\s*/dev/[sh]d", "redirect to block device"),
    (r"\bshred\b.*(?:/dev/|/boot)", "shred disk/boot"),
    (r"\bwipefs\b", "wipe filesystem signatures"),
    (r"\bparted\b.*\brm\b", "parted remove partition"),
    # Privilege escalation / download-and-execute
    (r"\bsudo\b", "sudo (set SHELL_ALLOW_SUDO=true to allow)"),
    (r"(?:curl|wget)\s+.*\|\s*(?:sudo\s+)?(?:ba)?sh", "curl/wget | sh"),
    (r"(?:curl|wget).*-[oO]-?\s*\|\s*(?:ba)?sh", "download | sh"),
    # Fork bomb
    (r":\(\)\s*\{", "fork bomb"),
    # Dangerous recursive permission changes at root
    (r"chmod\s+-[Rr].*\s+/(?:\s|$)", "chmod -R ... /"),
    (r"chown\s+-[Rr].*\s+/(?:\s|$)", "chown -R ... /"),
    # Accidental destruction
    (r"\bmv\b.*\s+/dev/null", "mv to /dev/null"),
]

# Sensitive read patterns (always blocked regardless of SHELL_ALLOW_SUDO)
_SENSITIVE_READ_PATTERNS: list[tuple[str, str]] = [
    (r"cat\s+.*\.ssh/", "read .ssh file"),
    (r"cat\s+.*\.aws/credentials", "read AWS credentials"),
]


def is_dangerous(command: str, allow_sudo: bool = False) -> tuple[bool, str]:
    """Check a single command string. Returns (blocked, reason)."""
    for pattern, desc in DANGEROUS_PATTERNS:
        if pattern == r"\bsudo\b" and allow_sudo:
            continue
        if re.search(pattern, command, re.IGNORECASE):
            return True, desc
    for pattern, desc in _SENSITIVE_READ_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, desc
    return False, ""


def is_script_dangerous(
    script: str, allow_sudo: bool = False
) -> tuple[bool, str, str]:
    """Check every non-comment line. Returns (blocked, reason, bad_line)."""
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        blocked, reason = is_dangerous(stripped, allow_sudo=allow_sudo)
        if blocked:
            return True, reason, stripped
    return False, "", ""


# ---------------------------------------------------------------------------
# Core subprocess runner
# ---------------------------------------------------------------------------

def find_bash() -> Optional[str]:
    r"""Locate a bash executable, or None.

    Order: $QUICKRUN_BASH, bash on PATH, then (Windows) Git for Windows.
    On Windows, C:\Windows\System32\bash.exe is the WSL launcher, which runs
    inside Linux with different paths, so it is skipped.
    """
    override = os.environ.get("QUICKRUN_BASH")
    if override and Path(override).is_file():
        return override
    found = shutil.which("bash")
    if found and not (IS_WINDOWS and "\\system32\\" in found.lower()):
        return found
    if not IS_WINDOWS:
        return None
    candidates: list[Path] = []
    git = shutil.which("git")
    if git:
        g = Path(git).resolve()
        # ...\Git\cmd\git.exe  or  ...\Git\mingw64\bin\git.exe
        for root in (g.parent.parent, g.parent.parent.parent):
            candidates += [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            candidates.append(Path(base) / "Git" / "bin" / "bash.exe")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Git" / "bin" / "bash.exe")
    candidates.append(Path(r"C:\Program Files\Git\bin\bash.exe"))
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


_NO_BASH_MSG = (
    "bash not found. On Windows install Git for Windows (it ships Git Bash) "
    "or set QUICKRUN_BASH to the full path of bash.exe."
)


def _run(
    args: list[str],
    cwd: Optional[str],
    timeout: int,
    max_output_chars: int,
) -> dict:
    """
    Run a command list, kill the whole process tree on timeout.
    Returns {stdout, stderr, return_code, truncated, duration_ms}.
    """
    t0 = time.monotonic()
    timed_out = False

    try:
        proc = subprocess.Popen(
            args,
            # Never let the command inherit the MCP server's stdin: that is the
            # MCP stdio pipe (on Windows a child touching it while the server
            # has a pending read hangs), and commands must not consume it.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            cwd=cwd,
            **new_group_kwargs(),  # own process group -> whole tree can be killed
        )
    except Exception as exc:
        return _err(f"Failed to start process: {exc}", t0)

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        try:
            proc.kill()
        except Exception:
            pass
        try:
            # A detached grandchild may still hold the pipes; don't hang on it.
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        rc = -1
        timed_out = True

    duration_ms = int((time.monotonic() - t0) * 1000)

    if timed_out:
        stderr = f"[TIMEOUT] 执行超过 {timeout}s，进程组已终止 / Process group killed after {timeout}s.\n" + (stderr or "")

    stdout, stderr, truncated = _truncate_pair(stdout or "", stderr or "", max_output_chars)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "return_code": rc,
        "truncated": truncated,
        "duration_ms": duration_ms,
    }


def _err(msg: str, t0: float) -> dict:
    return {
        "stdout": "",
        "stderr": msg,
        "return_code": -1,
        "truncated": False,
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }


def _blocked(reason: str) -> dict:
    return {
        "stdout": "",
        "stderr": (
            f"[BLOCKED] 命令被安全策略拦截 / Command blocked by safety policy: {reason}"
        ),
        "return_code": -1,
        "truncated": False,
        "duration_ms": 0,
    }


def _truncate_pair(stdout: str, stderr: str, limit: int) -> tuple[str, str, bool]:
    """Trim stdout+stderr so their combined length stays within limit."""
    combined = len(stdout) + len(stderr)
    if combined <= limit:
        return stdout, stderr, False

    # Allocate proportionally; at minimum give each side limit//4
    so_budget = max(limit // 4, int(limit * len(stdout) / max(combined, 1)))
    se_budget = limit - so_budget

    def _trim(s: str, budget: int) -> str:
        if len(s) <= budget:
            return s
        half = budget // 2
        omitted = len(s) - budget
        return s[:half] + f"\n…[{omitted} chars truncated]…\n" + s[-half:]

    return _trim(stdout, so_budget), _trim(stderr, se_budget), True


def _resolve_cwd(working_dir: Optional[str]) -> tuple[Optional[str], Optional[dict]]:
    """Return (cwd_str, None) or (None, error_dict)."""
    if not working_dir:
        return None, None
    cwd = str(Path(working_dir).expanduser().resolve())
    if not Path(cwd).is_dir():
        return None, {
            "stdout": "",
            "stderr": f"working_dir not found or not a directory: {cwd}",
            "return_code": -1,
            "truncated": False,
            "duration_ms": 0,
        }
    return cwd, None


# ---------------------------------------------------------------------------
# Sandbox profile temp-file helper
# ---------------------------------------------------------------------------

def _sandbox_prefix(config: Config) -> tuple[list[str], Optional[str]]:
    """Return (prefix_args, profile_path) or ([], None) if unavailable."""
    from .sandbox import generate_sbpl_profile, has_sandbox_exec

    if not has_sandbox_exec():
        return [], None

    profile = generate_sbpl_profile(
        workspace_dir=str(config.workspace_dir),
        allowed_folders=[str(f) for f in config.allowed_folders],
        with_write=True,
        allow_network=config.allow_network,
    )
    fd, path = tempfile.mkstemp(suffix=".sb", prefix="qce_shell_")
    with os.fdopen(fd, "w") as fh:
        fh.write(profile)
    return ["sandbox-exec", "-f", path], path


# ---------------------------------------------------------------------------
# Public API — called from server.py
# ---------------------------------------------------------------------------

def tool_run_command(
    command: str,
    working_dir: Optional[str],
    timeout: int,
    config: Config,
    allow_sudo: bool,
    use_sandbox: bool,
) -> dict:
    blocked, reason = is_dangerous(command, allow_sudo=allow_sudo)
    if blocked:
        return _blocked(reason)

    cwd, err = _resolve_cwd(working_dir)
    if err:
        return err

    profile_path: Optional[str] = None
    try:
        if use_sandbox:
            prefix, profile_path = _sandbox_prefix(config)
        else:
            prefix = []
        bash = find_bash()
        if bash:
            shell_args = [bash, "-c", command]
        elif IS_WINDOWS:
            # No Git Bash: run through cmd.exe so simple commands still work.
            shell_args = ["cmd.exe", "/d", "/s", "/c", command]
        else:
            return _err(_NO_BASH_MSG, time.monotonic())
        return _run(
            args=prefix + shell_args,
            cwd=cwd,
            timeout=timeout,
            max_output_chars=config.max_output_chars,
        )
    finally:
        if profile_path:
            try:
                os.unlink(profile_path)
            except OSError:
                pass


def tool_run_script(
    script: str,
    working_dir: Optional[str],
    timeout: int,
    config: Config,
    allow_sudo: bool,
    use_sandbox: bool,
) -> dict:
    blocked, reason, bad_line = is_script_dangerous(script, allow_sudo=allow_sudo)
    if blocked:
        return {
            **_blocked(reason),
            "stderr": _blocked(reason)["stderr"] + (f"\nLine: {bad_line}" if bad_line else ""),
        }

    cwd, err = _resolve_cwd(working_dir)
    if err:
        return err

    profile_path: Optional[str] = None
    try:
        if use_sandbox:
            prefix, profile_path = _sandbox_prefix(config)
        else:
            prefix = []
        bash = find_bash()
        if not bash:
            return _err(_NO_BASH_MSG, time.monotonic())
        return _run(
            args=prefix + [bash, "-c", script],
            cwd=cwd,
            timeout=timeout,
            max_output_chars=config.max_output_chars,
        )
    finally:
        if profile_path:
            try:
                os.unlink(profile_path)
            except OSError:
                pass


def tool_list_processes(filter_str: Optional[str], config: Config) -> dict:
    t0 = time.monotonic()
    cmd = ["tasklist"] if IS_WINDOWS else ["ps", "aux"]
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        lines = result.stdout.splitlines()
        if IS_WINDOWS:
            # tasklist: blank line, column titles, "=====" ruler, then rows.
            while lines and not lines[0].strip():
                lines.pop(0)
            header_n = next(
                (i + 1 for i, ln in enumerate(lines[:3]) if ln.startswith("=")), 1
            )
        else:
            header_n = 1
        if lines and filter_str:
            fl = filter_str.lower()
            header = lines[:header_n]
            body = [ln for ln in lines[header_n:] if fl in ln.lower()]
            output = "\n".join(header + body)
        else:
            output = "\n".join(lines)

        output, _, truncated = _truncate_pair(output, "", config.max_output_chars)

        return {
            "stdout": output,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "truncated": truncated,
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        return _err(f"list_processes error: {exc}", t0)
