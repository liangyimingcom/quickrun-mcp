# Security Policy

## Important: Code Runs Locally

QuickRun MCP executes Python and shell code **on your local machine**, not in a remote
cloud sandbox. Please read this section before deploying.

## Sandbox Layers

| Platform | Sandbox | Strength |
|---|---|---|
| macOS | `sandbox-exec` (SBPL profile, dynamically generated) | Hard — OS-enforced |
| Linux / Windows | `sys.addaudithook` | Soft — pure-Python, can be bypassed by C extensions |

## What Is Protected

- **Sensitive credential files** (`.ssh/`, `.aws/`, `Library/Keychains`, `.gnupg`, `.config/gh`, etc.)
  are blocked from reads **and** writes under macOS sandbox-exec.
- Write access is restricted to `WORKSPACE_DIR` (and optionally `ALLOWED_FOLDERS` for
  `*_with_write` tools).
- Shell tools (`run_command`, `run_script`) block a curated list of destructive patterns
  (see `shell_tools.py::DANGEROUS_PATTERNS`).

## What Is NOT Protected

- Code running in a persistent session (`run_python`) shares a Python namespace across
  calls within that session. Malicious code injected into one call can affect subsequent calls.
- The soft sandbox (Linux/Windows) can be bypassed by code that uses C extension modules
  to call OS functions directly.
- `SHELL_SANDBOX=true` applies sandbox-exec to shell commands on macOS, but is off by default.
- Network access is allowed by default (`ALLOW_NETWORK=true`). Set `ALLOW_NETWORK=false` to
  restrict outbound network calls.

## Recommended Hardening

1. Set `ALLOWED_FOLDERS` to only the directories you actually need.
2. Do not add directories containing secrets (SSH keys, cloud credentials, tokens) to
   `ALLOWED_FOLDERS`.
3. Keep `SHELL_ALLOW_SUDO=false` (default) in production.
4. Consider `SHELL_SANDBOX=true` on macOS for additional shell command isolation.
5. Review the AI agent's code before granting it access to sensitive directories.

## Reporting a Vulnerability

Open a GitHub Issue labeled **security** or contact the maintainer via GitHub private
message. Please do not publicly disclose security issues before they have been addressed.
