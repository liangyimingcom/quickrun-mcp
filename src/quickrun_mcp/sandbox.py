"""Sandbox implementations: macOS sandbox-exec (primary) + audit-hook fallback."""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Sensitive subpaths relative to $HOME that should never be readable/writable
SENSITIVE_SUBPATHS = [
    ".ssh",
    ".aws",
    "Library/Keychains",
    ".kiro",
    ".claude",
    ".gnupg",
    ".config/gh",
    "Library/Application Support/1Password",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".docker/config.json",
    ".bash_history",
    ".zsh_history",
    ".zshrc",         # might contain tokens/exports
]


def has_sandbox_exec() -> bool:
    """Return True if macOS sandbox-exec is available."""
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def _sensitive_paths(home: str) -> list[str]:
    return [str(Path(home) / p) for p in SENSITIVE_SUBPATHS]


def generate_sbpl_profile(
    workspace_dir: str,
    allowed_folders: list[str],
    with_write: bool,
    allow_network: bool,
) -> str:
    """Generate a macOS SBPL sandbox profile."""
    home = str(Path.home())
    sensitive = _sensitive_paths(home)

    lines = [
        "(version 1)",
        "(deny default)",
        "",
        "; Process operations required by Python",
        "(allow process-exec*)",
        "(allow process-fork)",
        "(allow signal)",
        "",
        "; Basic system operations",
        "(allow file-read-metadata)",
        "(allow mach-lookup)",
        "(allow ipc-posix-shm*)",
        "(allow sysctl-read)",
        "(allow system-socket)",
        "(allow file-ioctl)",
        "",
        "; Deny sensitive paths first (first-match wins in SBPL)",
    ]

    for path in sensitive:
        esc = path.replace('"', '\\"')
        lines.append(f'(deny file-read*  (subpath "{esc}"))')
        lines.append(f'(deny file-write* (subpath "{esc}"))')

    lines += [
        "",
        "; Allow all file reads (sensitive denies above take precedence)",
        "(allow file-read*)",
        "",
        "; Allow writes to system temp directories",
        '(allow file-write* (subpath "/tmp"))',
        '(allow file-write* (subpath "/private/tmp"))',
        '(allow file-write* (subpath "/var/folders"))',
        '(allow file-write* (subpath "/private/var/folders"))',
        '(allow file-write* (literal "/dev/null"))',
        "",
        "; Allow writes to workspace",
        f'(allow file-write* (subpath "{workspace_dir}"))',
    ]

    if with_write and allowed_folders:
        lines.append("")
        lines.append("; Allow writes to user-specified allowed folders")
        for folder in allowed_folders:
            esc = folder.replace('"', '\\"')
            lines.append(f'(allow file-write* (subpath "{esc}"))')

    lines.append("")
    if allow_network:
        lines.append("; Network allowed")
        lines.append("(allow network*)")
    else:
        lines.append("; Network denied (ALLOW_NETWORK=false)")

    return "\n".join(lines)


def build_sandboxed_command(
    python_exe: str,
    worker_script: str,
    extra_args: list[str],
    workspace_dir: str,
    allowed_folders: list[str],
    with_write: bool,
    allow_network: bool,
) -> tuple[list[str], str | None]:
    """Return (cmd_list, profile_tmp_path).

    Caller must delete profile_tmp_path when the process exits.
    If sandbox-exec is unavailable, returns a plain Python command and None.
    """
    if not has_sandbox_exec():
        logger.info("sandbox-exec not available; running without macOS sandbox")
        return (
            [python_exe, "-u", worker_script] + extra_args,
            None,
        )

    profile = generate_sbpl_profile(
        workspace_dir=workspace_dir,
        allowed_folders=allowed_folders,
        with_write=with_write,
        allow_network=allow_network,
    )

    fd, profile_path = tempfile.mkstemp(suffix=".sb", prefix="qce_sandbox_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(profile)
    except Exception:
        os.close(fd)
        raise

    cmd = [
        "sandbox-exec",
        "-f", profile_path,
        python_exe, "-u", worker_script,
    ] + extra_args

    return cmd, profile_path


# ---------------------------------------------------------------------------
# Fallback: sys.addaudithook (runs inside the worker subprocess, not the server)
# ---------------------------------------------------------------------------

def install_audit_hook(writable_paths: list[str], sensitive_paths: list[str]) -> None:
    """
    Install a sys.addaudithook to restrict file writes to allowed paths.
    This is a soft sandbox (C extensions can bypass it) but provides basic protection.
    Called from worker_process.py on non-macOS or when sandbox-exec is unavailable.
    """
    import sys as _sys

    def _norm(p: str) -> str:
        # normcase: case-insensitive comparison on Windows
        return os.path.normcase(os.path.realpath(p))

    def _under(path: str, root: str) -> bool:
        # Component-aware prefix match: /a/b covers /a/b/c but not /a/bc.
        return path == root or path.startswith(root.rstrip("\\/") + os.sep)

    norm_writable = [_norm(p) for p in writable_paths]
    norm_sensitive = [_norm(p) for p in sensitive_paths]
    _tmp_roots = [
        _norm(t) for t in (
            "/tmp", "/private/tmp", "/var/folders", "/private/var/folders",
            tempfile.gettempdir(),
        )
    ] + [_norm(os.devnull)]

    def _allowed_write(path: str) -> bool:
        real = _norm(path)
        if any(_under(real, t) for t in _tmp_roots):
            return True
        return any(_under(real, w) for w in norm_writable)

    def _is_sensitive(path: str) -> bool:
        real = _norm(path)
        return any(_under(real, s) for s in norm_sensitive)

    _WRITE_FLAGS = (
        getattr(os, "O_WRONLY", 1)
        | getattr(os, "O_RDWR", 2)
        | getattr(os, "O_CREAT", 64)
        | getattr(os, "O_TRUNC", 512)
    )

    def _audit(event: str, args: tuple) -> None:  # noqa: ANN001
        if event == "open":
            path = str(args[0]) if args else ""
            if _is_sensitive(path):
                raise PermissionError(f"Sensitive path blocked: {path}")
            flags = args[1] if len(args) > 1 else 0
            if isinstance(flags, int) and (flags & _WRITE_FLAGS):
                if not _allowed_write(path):
                    raise PermissionError(f"Write not allowed outside permitted paths: {path}")
        elif event in ("os.rename", "os.replace"):
            dst = str(args[1]) if len(args) > 1 else ""
            if _is_sensitive(dst) or not _allowed_write(dst):
                raise PermissionError(f"Move/rename not allowed to: {dst}")
        elif event in ("os.remove", "os.unlink", "os.rmdir", "shutil.rmtree"):
            path = str(args[0]) if args else ""
            if _is_sensitive(path) or not _allowed_write(path):
                raise PermissionError(f"Delete not allowed: {path}")

    _sys.addaudithook(_audit)
    logger.info("Fallback audit hook installed (soft sandbox)")
