#!/usr/bin/env python3
"""
QuickRun MCP — zero-install entry point.

Usage (requires uv, downloads dependencies automatically):

  # Minimal — Python execution tools only:
  uv run --with "mcp>=1.0" /path/to/run_server.py

  # Full — includes data-analysis packages:
  uv run \\
    --with "mcp>=1.0" --with pandas --with numpy --with openpyxl \\
    --with matplotlib --with Pillow --with requests --with PyYAML \\
    --with duckdb --with pdfplumber --with python-docx --with python-pptx \\
    /path/to/run_server.py

Environment variables:
  WORKSPACE_DIR        default: ~/.quickrun/workspace
  ALLOWED_FOLDERS      colon-separated paths (semicolon on Windows)
  DEFAULT_TIMEOUT      seconds, default 60
  MAX_OUTPUT_CHARS     default 61440 (60 KB)
  ALLOW_NETWORK        true/false, default true
  ENABLE_SHELL_TOOLS   true/false, default true
  SHELL_ALLOW_SUDO     true/false, default false
  SHELL_SANDBOX        true/false, default false (apply sandbox-exec to shell cmds)
"""

import sys
from pathlib import Path

# Put src/ on the path so the package is importable without prior installation
_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from quickrun_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
