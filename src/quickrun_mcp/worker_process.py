#!/usr/bin/env python3
"""
Worker subprocess for quickrun-mcp.

Usage:
  python worker_process.py              # persistent mode (default)
  python worker_process.py --once       # stateless mode: read stdin once, run, exit

Wire protocol (line-delimited JSON):
  Input  → {"code": "...", "workspace_dir": "..."}
  Output ← {"stdout": "...", "stderr": "...", "error": null, "files": [...]}

Environment variables consumed:
  USE_AUDIT_HOOK=1       install fallback audit hook (set by executor when sandbox-exec absent)
  WRITABLE_PATHS=p1:p2   paths allowed for writing (for audit hook)
  SENSITIVE_PATHS=p1:p2  paths blocked for all access (for audit hook)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import sys
import traceback

# ---------------------------------------------------------------------------
# Parse mode flag FIRST (before we redirect stdin)
# ---------------------------------------------------------------------------
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--once", action="store_true")
_args, _ = _parser.parse_known_args()

# ---------------------------------------------------------------------------
# Save real stdio for communication
# ---------------------------------------------------------------------------
_comm_in = sys.stdin
_comm_out = sys.stdout

# ---------------------------------------------------------------------------
# Optionally install soft-sandbox audit hook
# ---------------------------------------------------------------------------
if os.environ.get("USE_AUDIT_HOOK") == "1":
    _writable_paths = [
        p for p in os.environ.get("WRITABLE_PATHS", "").split(":") if p
    ]
    _sensitive_paths = [
        p for p in os.environ.get("SENSITIVE_PATHS", "").split(":") if p
    ]
    # Import from the package only if available; otherwise inline a minimal version
    try:
        from quickrun_mcp.sandbox import install_audit_hook
        install_audit_hook(_writable_paths, _sensitive_paths)
    except ImportError:
        pass  # sandbox module not importable in this context; skip

# ---------------------------------------------------------------------------
# In persistent mode: redirect stdin so user code cannot read our pipe
# ---------------------------------------------------------------------------
if not _args.once:
    try:
        sys.stdin = open(os.devnull, "r")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot(directory: str) -> dict[str, float]:
    """Return {rel_path: mtime} for all files under directory."""
    result: dict[str, float] = {}
    base = pathlib.Path(directory)
    if not base.exists():
        return result
    try:
        for f in base.rglob("*"):
            if f.is_file():
                try:
                    result[str(f.relative_to(base))] = f.stat().st_mtime
                except (OSError, ValueError):
                    pass
    except OSError:
        pass
    return result


def _diff(before: dict[str, float], after: dict[str, float]) -> list[str]:
    return sorted(
        p for p, mt in after.items()
        if p not in before or before[p] != mt
    )


def _run(code: str, workspace_dir: str, namespace: dict) -> dict:
    """Execute *code* in *namespace*; return result dict."""
    namespace.setdefault("WORKSPACE_DIR", workspace_dir)

    # Ensure workspace dirs exist
    ws = pathlib.Path(workspace_dir)
    try:
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "artifacts").mkdir(exist_ok=True)
        (ws / "tmp").mkdir(exist_ok=True)
    except OSError:
        pass

    # Change CWD — use explicit working_dir if provided, else workspace_dir
    working_dir = namespace.get("_working_dir") or workspace_dir
    old_cwd: str | None = None
    try:
        old_cwd = os.getcwd()
        os.chdir(working_dir)
    except OSError:
        old_cwd = None

    before = _snapshot(workspace_dir)

    # Capture stdout / stderr
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    error: str | None = None
    try:
        exec(compile(code, "<user_code>", "exec"), namespace)  # noqa: S102
    except SystemExit as exc:
        error = f"SystemExit({exc.code})"
    except Exception:
        error = traceback.format_exc()
    finally:
        stdout_val = sys.stdout.getvalue()
        stderr_val = sys.stderr.getvalue()
        sys.stdout = old_out
        sys.stderr = old_err

    if old_cwd:
        try:
            os.chdir(old_cwd)
        except OSError:
            pass

    after = _snapshot(workspace_dir)
    return {
        "stdout": stdout_val,
        "stderr": stderr_val,
        "error": error,
        "files": _diff(before, after),
    }


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def _run_once() -> None:
    """Read all of stdin as one JSON message, execute, write result, exit."""
    try:
        raw = sys.stdin.read()
        msg = json.loads(raw)
    except Exception as exc:
        result = {"stdout": "", "stderr": "", "error": f"Input parse error: {exc}", "files": []}
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()
        return

    code = msg.get("code", "")
    workspace_dir = msg.get("workspace_dir", "")
    working_dir = msg.get("working_dir") or workspace_dir
    ns: dict = {"_working_dir": working_dir}
    result = _run(code, workspace_dir, ns)
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


def _run_persistent() -> None:
    """Main loop: read JSON lines from pipe, execute in shared namespace, reply."""
    namespace: dict = {}

    while True:
        try:
            line = _comm_in.readline()
        except (EOFError, OSError):
            break

        if not line:
            break  # parent closed pipe

        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = {"stdout": "", "stderr": "", "error": f"JSON error: {exc}", "files": []}
            try:
                _comm_out.write(json.dumps(resp) + "\n")
                _comm_out.flush()
            except OSError:
                break
            continue

        code = msg.get("code", "")
        workspace_dir = msg.get("workspace_dir", "")
        working_dir = msg.get("working_dir") or workspace_dir
        namespace["_working_dir"] = working_dir
        result = _run(code, workspace_dir, namespace)

        try:
            _comm_out.write(json.dumps(result) + "\n")
            _comm_out.flush()
        except (BrokenPipeError, OSError):
            break


if _args.once:
    _run_once()
else:
    _run_persistent()
