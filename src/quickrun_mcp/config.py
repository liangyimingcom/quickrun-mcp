"""Configuration from environment variables."""

import os
from pathlib import Path

from ._proc import split_paths


class Config:
    def __init__(self) -> None:
        default_workspace = Path.home() / ".quickrun" / "workspace"
        self.workspace_dir = Path(
            os.environ.get("WORKSPACE_DIR", str(default_workspace))
        )

        # PATH-style list: ':' on macOS/Linux, ';' on Windows (os.pathsep).
        # Splitting on ':' everywhere broke Windows drive letters
        # ("C:\\x" became "C" and "\\x").
        allowed_raw = os.environ.get("ALLOWED_FOLDERS", "")
        self.allowed_folders: list[Path] = [
            Path(p) for p in split_paths(allowed_raw)
        ]

        self.default_timeout = int(os.environ.get("DEFAULT_TIMEOUT", "60"))
        self.max_output_chars = int(
            os.environ.get("MAX_OUTPUT_CHARS", str(60 * 1024))
        )
        self.allow_network = os.environ.get("ALLOW_NETWORK", "true").lower() in (
            "true", "1", "yes"
        )

    def __repr__(self) -> str:
        return (
            f"Config(workspace={self.workspace_dir}, "
            f"allowed_folders={self.allowed_folders}, "
            f"timeout={self.default_timeout}, "
            f"max_output={self.max_output_chars}, "
            f"network={self.allow_network})"
        )
