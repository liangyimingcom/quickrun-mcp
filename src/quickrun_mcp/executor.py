"""Execution engine: PersistentWorker and StatelessExecutor."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from ._proc import join_paths, kill_tree, new_group_kwargs
from .config import Config
from .sandbox import _sensitive_paths, build_sandboxed_command, has_sandbox_exec

logger = logging.getLogger(__name__)

WORKER_SCRIPT = str(Path(__file__).parent / "worker_process.py")

# asyncio StreamReader buffer — must be > max response JSON (which can be ~60 KB stdout + overhead)
_STREAM_LIMIT = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    omitted = len(text) - max_chars
    return (
        text[:half]
        + f"\n\n… [TRUNCATED — {omitted:,} chars omitted; total {len(text):,}] …\n\n"
        + text[-half:]
    )


def _format_result(
    result: dict,
    max_output_chars: int,
    duration_ms: int = 0,
) -> str:
    parts: list[str] = []

    stdout = (result.get("stdout") or "").rstrip()
    stderr = (result.get("stderr") or "").rstrip()
    error = result.get("error")
    files: list[str] = result.get("files") or []

    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    if error:
        parts.append(f"[error]\n{error}")

    combined = "\n".join(parts)
    combined = _truncate(combined, max_output_chars)

    if files:
        shown = files[:50]
        file_lines = "\n".join(f"  {f}" for f in shown)
        if len(files) > 50:
            file_lines += f"\n  … and {len(files) - 50} more"
        combined += f"\n\n[workspace files changed/created]\n{file_lines}"

    # Metadata footer (matches shell-tools style: return_code + duration)
    rc = 1 if error else 0
    combined += f"\n[return_code={rc} | duration={duration_ms}ms]"

    return combined or "(no output)"


def _validate_working_dir(
    requested: str, config: Config
) -> tuple[Optional[str], Optional[str]]:
    """Return (resolved_path, None) or (None, error_message)."""
    real = Path(requested).expanduser().resolve()
    if not real.is_dir():
        return None, f"working_dir not found: {real}"

    allowed_roots = [config.workspace_dir.resolve()] + [
        a.resolve() for a in config.allowed_folders
    ]
    for root in allowed_roots:
        try:
            real.relative_to(root)
            return str(real), None
        except ValueError:
            pass

    return None, (
        f"working_dir '{real}' is not inside WORKSPACE_DIR or ALLOWED_FOLDERS. "
        f"Allowed roots: {[str(r) for r in allowed_roots]}"
    )


def _kill_now(proc: asyncio.subprocess.Process) -> None:
    """Synchronously kill *proc* and its children. Never raises, on any OS.

    Synchronous on purpose: it is also used while the calling task is being
    cancelled, where further awaits may be cancelled as well.
    """
    if proc.returncode is None:
        kill_tree(proc.pid)
        try:
            proc.kill()
        except Exception:
            pass


async def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    """Kill the process tree, then wait for it to exit."""
    _kill_now(proc)
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except Exception:
        pass


def _worker_env(config: Config, with_write: bool) -> dict[str, str]:
    """Build environment for the worker subprocess."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    if not has_sandbox_exec():
        env["USE_AUDIT_HOOK"] = "1"
        writable = [str(config.workspace_dir)]
        if with_write:
            writable += [str(f) for f in config.allowed_folders]
        env["WRITABLE_PATHS"] = join_paths(writable)
        home = str(Path.home())
        env["SENSITIVE_PATHS"] = join_paths(_sensitive_paths(home))

    return env


# ---------------------------------------------------------------------------
# Persistent worker (Jupyter-kernel-like)
# ---------------------------------------------------------------------------

class PersistentWorker:
    """
    Long-running worker subprocess that preserves Python namespace across calls.
    Auto-restarts on crash or timeout.
    """

    def __init__(self, config: Config, with_write: bool = False) -> None:
        self.config = config
        self.with_write = with_write
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._profile_path: Optional[str] = None
        self._lock = asyncio.Lock()

    def _build_cmd(self) -> tuple[list[str], Optional[str]]:
        return build_sandboxed_command(
            python_exe=sys.executable,
            worker_script=WORKER_SCRIPT,
            extra_args=[],
            workspace_dir=str(self.config.workspace_dir),
            allowed_folders=[str(f) for f in self.config.allowed_folders],
            with_write=self.with_write,
            allow_network=self.config.allow_network,
        )

    async def _ensure(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        if self._proc is not None:
            logger.warning("Worker exited (rc=%s), restarting", self._proc.returncode)
            await self._cleanup_proc()

        cmd, profile_path = self._build_cmd()
        self._profile_path = profile_path
        env = _worker_env(self.config, self.with_write)

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            limit=_STREAM_LIMIT,
            **new_group_kwargs(),
        )

    def _discard_now(self) -> None:
        """Tear the worker down synchronously (safe inside a cancelled task)."""
        proc, self._proc = self._proc, None
        if proc is not None:
            _kill_now(proc)
        if self._profile_path:
            try:
                os.unlink(self._profile_path)
            except OSError:
                pass
            self._profile_path = None

    async def _read_reply(self, req_id: str) -> Optional[dict]:
        """Read worker output until the reply tagged *req_id*; None on EOF.

        Lines that are not ours (a reply to an earlier, abandoned request, or
        anything else) are discarded, so a late reply can never be returned
        as the answer to a later call.
        """
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            raw = await self._proc.stdout.readline()
            if not raw:
                return None
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                logger.warning("Ignoring non-protocol line from worker: %r", raw[:200])
                continue
            if isinstance(obj, dict) and obj.get("id") == req_id:
                return obj
            logger.warning(
                "Discarding stale worker reply (id=%s)",
                obj.get("id") if isinstance(obj, dict) else "?",
            )

    async def _cleanup_proc(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            await _kill_proc(proc)
        if self._profile_path:
            try:
                os.unlink(self._profile_path)
            except OSError:
                pass
            self._profile_path = None

    async def execute(
        self,
        code: str,
        timeout: int,
        working_dir: Optional[str] = None,
    ) -> str:
        # Validate working_dir before acquiring lock
        resolved_cwd: Optional[str] = None
        if working_dir:
            resolved_cwd, err_msg = _validate_working_dir(working_dir, self.config)
            if err_msg:
                return _format_result(
                    {"stdout": "", "stderr": "", "error": err_msg, "files": []},
                    self.config.max_output_chars,
                    duration_ms=0,
                )

        t0 = time.monotonic()
        req_id = uuid.uuid4().hex
        async with self._lock:
            try:
                return await self._execute_locked(code, timeout, resolved_cwd, req_id, t0)
            except BaseException:
                # Cancelled (e.g. the MCP client gave up on the request) or an
                # unexpected error. The worker may still be running the code and
                # would later write its reply; kill it now so nothing it does
                # can leak into the next call.
                self._discard_now()
                raise

    async def _execute_locked(
        self,
        code: str,
        timeout: int,
        resolved_cwd: Optional[str],
        req_id: str,
        t0: float,
    ) -> str:
        await self._ensure()

        msg = (json.dumps({
            "id": req_id,
            "code": code,
            "workspace_dir": str(self.config.workspace_dir),
            "working_dir": resolved_cwd or str(self.config.workspace_dir),
        }) + "\n").encode()

        assert self._proc is not None
        try:
            self._proc.stdin.write(msg)
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError):
            await self._cleanup_proc()
            await self._ensure()
            self._proc.stdin.write(msg)
            await self._proc.stdin.drain()

        try:
            result = await asyncio.wait_for(
                self._read_reply(req_id),
                timeout=float(timeout) + 2.0,
            )
        except asyncio.TimeoutError:
            await self._cleanup_proc()
            duration_ms = int((time.monotonic() - t0) * 1000)
            return _format_result(
                {
                    "stdout": "", "stderr": "",
                    "error": (
                        f"TimeoutError: execution exceeded {timeout}s. "
                        "Worker killed; session reset (all variables lost)."
                    ),
                    "files": [],
                },
                self.config.max_output_chars,
                duration_ms=duration_ms,
            )

        if result is None:
            await self._cleanup_proc()
            duration_ms = int((time.monotonic() - t0) * 1000)
            return _format_result(
                {"stdout": "", "stderr": "", "error": "Worker died unexpectedly.", "files": []},
                self.config.max_output_chars,
                duration_ms=duration_ms,
            )

        duration_ms = int((time.monotonic() - t0) * 1000)
        return _format_result(result, self.config.max_output_chars, duration_ms=duration_ms)

    async def reset(self) -> str:
        async with self._lock:
            await self._cleanup_proc()
        return "Session reset — all variables cleared."

    async def cleanup(self) -> None:
        async with self._lock:
            await self._cleanup_proc()


# ---------------------------------------------------------------------------
# Stateless executor (fresh process each call)
# ---------------------------------------------------------------------------

class StatelessExecutor:
    """Runs code in a fresh subprocess every call — no state between calls."""

    def __init__(self, config: Config, with_write: bool = False) -> None:
        self.config = config
        self.with_write = with_write

    async def execute(
        self,
        code: str,
        timeout: int,
        working_dir: Optional[str] = None,
    ) -> str:
        # Validate working_dir
        resolved_cwd: Optional[str] = None
        if working_dir:
            resolved_cwd, err_msg = _validate_working_dir(working_dir, self.config)
            if err_msg:
                return _format_result(
                    {"stdout": "", "stderr": "", "error": err_msg, "files": []},
                    self.config.max_output_chars,
                    duration_ms=0,
                )

        t0 = time.monotonic()
        profile_path: Optional[str] = None
        try:
            cmd, profile_path = build_sandboxed_command(
                python_exe=sys.executable,
                worker_script=WORKER_SCRIPT,
                extra_args=["--once"],
                workspace_dir=str(self.config.workspace_dir),
                allowed_folders=[str(f) for f in self.config.allowed_folders],
                with_write=self.with_write,
                allow_network=self.config.allow_network,
            )

            env = _worker_env(self.config, self.with_write)
            msg = json.dumps({
                "code": code,
                "workspace_dir": str(self.config.workspace_dir),
                "working_dir": resolved_cwd or str(self.config.workspace_dir),
            }).encode()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=_STREAM_LIMIT,
                **new_group_kwargs(),
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=msg),
                    timeout=float(timeout) + 2.0,
                )
            except asyncio.CancelledError:
                _kill_now(proc)
                raise
            except asyncio.TimeoutError:
                await _kill_proc(proc)
                duration_ms = int((time.monotonic() - t0) * 1000)
                return _format_result(
                    {"stdout": "", "stderr": "", "error": f"TimeoutError: exceeded {timeout}s.", "files": []},
                    self.config.max_output_chars,
                    duration_ms=duration_ms,
                )

            stdout_text = (stdout_b or b"").decode("utf-8", errors="replace").strip()
            stderr_text = (stderr_b or b"").decode("utf-8", errors="replace").strip()

            if not stdout_text:
                duration_ms = int((time.monotonic() - t0) * 1000)
                return _format_result(
                    {"stdout": "", "stderr": stderr_text, "error": "Worker produced no output (crash?)", "files": []},
                    self.config.max_output_chars,
                    duration_ms=duration_ms,
                )

            try:
                result = json.loads(stdout_text)
            except json.JSONDecodeError:
                result = {"stdout": stdout_text, "stderr": stderr_text, "error": None, "files": []}

            duration_ms = int((time.monotonic() - t0) * 1000)
            return _format_result(result, self.config.max_output_chars, duration_ms=duration_ms)

        finally:
            if profile_path:
                try:
                    os.unlink(profile_path)
                except OSError:
                    pass
