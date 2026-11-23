"""
MCP server — exposes Quick Code Execution tools over stdio.

Tools (10 total):
  Python execution (persistent session):
    run_python, run_python_with_write, reset_python_session
  Python execution (stateless / on-device):
    run_python_on_device, run_python_on_device_with_write
  Shell execution (compatible with common shell-runner MCP servers):
    run_command, run_script, list_processes
  Introspection:
    list_allowed_folders, list_installed_packages

Environment variables:
  WORKSPACE_DIR, ALLOWED_FOLDERS, DEFAULT_TIMEOUT, MAX_OUTPUT_CHARS, ALLOW_NETWORK
  ENABLE_SHELL_TOOLS  (default true)  — set false to hide shell tools
  SHELL_ALLOW_SUDO    (default false) — set true to allow sudo in shell commands
  SHELL_SANDBOX       (default false) — set true to apply sandbox-exec to shell commands
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP as _MCPApp       # mcp < 2
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as _MCPApp   # mcp >= 2

from .config import Config
from .executor import PersistentWorker, StatelessExecutor
from .sandbox import has_sandbox_exec

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool annotations
# ---------------------------------------------------------------------------
try:
    from mcp.types import ToolAnnotations as _TA
    _ANN_RO = _TA(readOnlyHint=True)
    _ANN_RW = _TA(readOnlyHint=False, destructiveHint=False)
except Exception:
    _ANN_RO = None  # type: ignore[assignment]
    _ANN_RW = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Config and global flags
# ---------------------------------------------------------------------------
_config = Config()
_ENABLE_SHELL = os.environ.get("ENABLE_SHELL_TOOLS", "true").lower() not in ("false", "0", "no")
_ALLOW_SUDO   = os.environ.get("SHELL_ALLOW_SUDO",   "false").lower() in ("true", "1", "yes")
_SHELL_SANDBOX = os.environ.get("SHELL_SANDBOX",     "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Worker instances
# ---------------------------------------------------------------------------
_basic_worker = PersistentWorker(_config, with_write=False)
_write_worker = PersistentWorker(_config, with_write=True)
_stateless_ro = StatelessExecutor(_config, with_write=False)
_stateless_rw = StatelessExecutor(_config, with_write=True)

sandbox_mode = "macOS sandbox-exec" if has_sandbox_exec() else "audit-hook fallback"
logger.warning(
    "Sandbox: %s | workspace: %s | shell_tools: %s | shell_sandbox: %s",
    sandbox_mode, _config.workspace_dir, _ENABLE_SHELL, _SHELL_SANDBOX,
)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = _MCPApp(
    "quickrun",
    description=(
        "Local code-execution MCP server. "
        "Replicates AWS Quick's Code Execution + Local Code Execution tools "
        "and is drop-in compatible with common shell-runner MCP servers (run_command / run_script / list_processes)."
    ),
)


# ============================================================
# Python persistent-session tools
# ============================================================

@mcp.tool(annotations=_ANN_RW)
async def run_python(
    code: str,
    timeout: int = 60,
    working_dir: Optional[str] = None,
) -> str:
    """在**持久 Python 会话**中执行代码（类似 Jupyter kernel）。
    Execute Python code in a **persistent session** (Jupyter-kernel semantics).

    跨调用保留变量、函数、import。适合迭代分析、数据处理、可视化。
    Variables, functions, and imports survive across calls until reset.
    Use for iterative data analysis, computation, and visualization.

    - CWD = WORKSPACE_DIR（也作变量 `WORKSPACE_DIR` 注入）
    - 读取：workspace + allowed folders（只读）
    - 写入：仅 workspace (artifacts/, tmp/)
    - 输出上限 60 KB；超时后会话自动重置（变量丢失）
    - working_dir（可选）：必须在 WORKSPACE_DIR 或 ALLOWED_FOLDERS 内
    - Output capped 60 KB; timeout resets session (all vars lost)
    - timeout 上限为 DEFAULT_TIMEOUT（默认 60s）/ capped at DEFAULT_TIMEOUT (default 60s)
    - return_code=0 success, 1 exception; duration_ms in footer
    """
    effective = max(1, min(timeout, _config.default_timeout))
    return await _basic_worker.execute(code, effective, working_dir=working_dir)


@mcp.tool(annotations=_ANN_RW)
async def run_python_with_write(
    code: str,
    timeout: int = 60,
    working_dir: Optional[str] = None,
) -> str:
    """同 `run_python`，但代码可**写入 allowed folders**。
    Same as `run_python` but code may also **write to allowed folders**.

    当结果需要保存到用户目录（如 ~/Downloads）时使用。
    Use when results must be saved directly to a user directory (e.g. ~/Downloads).

    - 读写：workspace + ALLOWED_FOLDERS
    - working_dir 须在 WORKSPACE_DIR 或 ALLOWED_FOLDERS 内
    """
    effective = max(1, min(timeout, _config.default_timeout))
    return await _write_worker.execute(code, effective, working_dir=working_dir)


@mcp.tool(annotations=_ANN_RW)
async def run_python_on_device(
    code: str,
    timeout: int = 60,
    working_dir: Optional[str] = None,
) -> str:
    """每次启动**新进程**执行代码，调用间无状态。
    Execute Python in a **fresh process** — no state between calls.

    适合读取本地大文件（CSV、PDF、图片等），避免占用持久会话内存。
    Preferred for reading large local files from allowed folders without
    polluting the persistent session.

    - 读取：workspace + allowed folders（只读）
    - 写入：仅 workspace
    - 超时上限 270s
    """
    effective = max(1, min(timeout, 270))
    return await _stateless_ro.execute(code, effective, working_dir=working_dir)


@mcp.tool(annotations=_ANN_RW)
async def run_python_on_device_with_write(
    code: str,
    timeout: int = 60,
    working_dir: Optional[str] = None,
) -> str:
    """同 `run_python_on_device`，但可**写入 allowed folders**。
    Same as `run_python_on_device` but may also write to allowed folders.

    - 读写：workspace + ALLOWED_FOLDERS
    - 超时上限 270s
    """
    effective = max(1, min(timeout, 270))
    return await _stateless_rw.execute(code, effective, working_dir=working_dir)


@mcp.tool()
async def reset_python_session() -> str:
    """重置持久 Python 会话，清空所有变量。
    Reset persistent Python session — clears all variables.

    终止并重启 run_python / run_python_with_write 使用的 worker 进程。
    Kills and restarts the workers used by run_python and run_python_with_write.
    """
    r1 = await _basic_worker.reset()
    r2 = await _write_worker.reset()
    return f"{r1}\n{r2}"


# ============================================================
# Shell tools (compatible with common shell-runner MCP servers)
# Conditionally registered based on ENABLE_SHELL_TOOLS env var.
# ============================================================

if _ENABLE_SHELL:
    from .shell_tools import tool_run_command, tool_run_script, tool_list_processes

    @mcp.tool(annotations=_ANN_RW)
    async def run_command(
        command: str,
        working_dir: Optional[str] = None,
        timeout: int = 30,
    ) -> dict:
        """执行单条 shell 命令。
        Execute a single shell command.

        **何时用 run_command vs run_python？**
        用 run_command：调用系统工具（git、ffmpeg、brew、ls、grep …）。
        用 run_python：数据分析、文件解析、需要持久变量的计算。
        When to use run_command vs run_python?
        Use run_command: system tools (git, ffmpeg, brew, ls, grep …).
        Use run_python: data analysis, file parsing, stateful computation.

        - 危险命令自动拦截（rm -rf /、fork bomb、curl|sh …）
        - 默认拦截 sudo；设 SHELL_ALLOW_SUDO=true 放开
        - 超时 killpg 整个进程组（含子进程）
        - 返回 {stdout, stderr, return_code, truncated, duration_ms}
        - Dangerous patterns blocked (rm -rf /, fork bomb, curl|sh …)
        - sudo blocked by default; set SHELL_ALLOW_SUDO=true to allow
        - Timeout kills entire process group (including children)
        - Returns {stdout, stderr, return_code, truncated, duration_ms}
        """
        import asyncio
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: tool_run_command(
                command=command,
                working_dir=working_dir,
                timeout=timeout,
                config=_config,
                allow_sudo=_ALLOW_SUDO,
                use_sandbox=_SHELL_SANDBOX,
            ),
        )

    @mcp.tool(annotations=_ANN_RW)
    async def run_script(
        script: str,
        working_dir: Optional[str] = None,
        timeout: int = 60,
    ) -> dict:
        """执行多行 bash 脚本。
        Execute a multi-line bash script.

        每行独立进行危险命令检查。超时后 killpg 整个进程组。
        Each line is checked individually for dangerous patterns.
        Timeout kills entire process group.

        - 适合：多步骤 shell 操作、管道、条件逻辑
        - Use for: multi-step shell operations, pipes, conditional logic
        - 返回 {stdout, stderr, return_code, truncated, duration_ms}
        """
        import asyncio
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: tool_run_script(
                script=script,
                working_dir=working_dir,
                timeout=timeout,
                config=_config,
                allow_sudo=_ALLOW_SUDO,
                use_sandbox=_SHELL_SANDBOX,
            ),
        )

    @mcp.tool(annotations=_ANN_RO)
    async def list_processes(filter: Optional[str] = None) -> dict:
        """列出当前运行的进程（ps aux），支持名称过滤。
        List running processes (ps aux), optionally filtered by name.

        - filter：大小写不敏感的子串过滤 / case-insensitive substring filter
        - 返回 {stdout: 进程列表, stderr, return_code, truncated, duration_ms}
        """
        import asyncio
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: tool_list_processes(filter_str=filter, config=_config),
        )


# ============================================================
# Introspection tools (read-only)
# ============================================================

@mcp.tool(annotations=_ANN_RO)
async def list_allowed_folders() -> str:
    """列出可访问的目录。
    List workspace and allowed folders accessible to execution tools.

    返回 WORKSPACE_DIR（始终可写）和 ALLOWED_FOLDERS（通过 *_with_write 工具可写）。
    Returns WORKSPACE_DIR (always writable) and ALLOWED_FOLDERS
    (writable via *_with_write tools).
    """
    lines = [f"WORKSPACE_DIR: {_config.workspace_dir}"]
    if _config.allowed_folders:
        lines.append("\nAllowed folders (readable + writable with *_with_write):")
        for f in _config.allowed_folders:
            lines.append(f"  {f}")
    else:
        lines.append(
            "\nNo additional allowed folders configured.\n"
            f"Set ALLOWED_FOLDERS=path1{os.pathsep}path2 to add folders "
            "(';' separates paths on Windows, ':' elsewhere)."
        )
    return "\n".join(lines)


@mcp.tool(annotations=_ANN_RO)
async def list_installed_packages() -> str:
    """列出执行环境已安装的 Python 包（pip list）。
    List Python packages installed in the execution environment (pip list).

    在运行需要特定库的代码前，可用此工具确认包是否已安装。
    Use before running code that imports a library to verify it is available.
    """
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=columns"],
            stdin=subprocess.DEVNULL,  # never inherit the MCP stdio pipe
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout or result.stderr or "(no output from pip)"
        if len(output) > 60_000:
            output = output[:60_000] + "\n… (truncated)"
        return output
    except Exception as exc:
        return f"Error listing packages: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the MCP server on stdio."""
    ws = _config.workspace_dir
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "artifacts").mkdir(exist_ok=True)
    (ws / "tmp").mkdir(exist_ok=True)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
