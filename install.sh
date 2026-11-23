#!/usr/bin/env bash
# QuickRun MCP installer
#
# One-line install (from GitHub):
#   curl -fsSL https://raw.githubusercontent.com/liangyimingcom/quickrun-mcp/main/install.sh | bash
#
# Local install (from cloned repo):
#   bash install.sh
#
# Re-run to upgrade. Safe to run multiple times.
set -euo pipefail

REPO_URL="https://github.com/liangyimingcom/quickrun-mcp"
INSTALL_BASE="${QUICKRUN_HOME:-$HOME/.quickrun}"
SRC_DIR="$INSTALL_BASE/src/quickrun-mcp"
VENV_DIR="$INSTALL_BASE/venv"
WORKSPACE_DIR="$INSTALL_BASE/workspace"

echo "╔══════════════════════════════════════════════════════╗"
echo "║           QuickRun MCP Installer                     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Install dir : $INSTALL_BASE"
echo "  Workspace   : $WORKSPACE_DIR"
echo ""

# ── Detect source directory ───────────────────────────────
# If running via curl, BASH_SOURCE[0] is a temp file; we need to clone.
# If running locally (bash install.sh), SCRIPT_DIR is the repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q 'quickrun-mcp' "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
    LOCAL_REPO="$SCRIPT_DIR"
    echo "  Source      : local ($LOCAL_REPO)"
else
    LOCAL_REPO=""
    echo "  Source      : GitHub ($REPO_URL)"
fi

# ── Check Python ─────────────────────────────────────────
for py_candidate in python3 python; do
    if command -v "$py_candidate" &>/dev/null; then
        PYTHON="$py_candidate"; break
    fi
done
if [ -z "${PYTHON:-}" ]; then
    echo "ERROR: python3 not found. Install Python 3.10+ and retry."
    exit 1
fi

PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
PY_VER="$PY_MAJOR.$PY_MINOR"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ required (found $PY_VER)."
    exit 1
fi
echo "  Python      : $PYTHON ($PY_VER)"

# ── Clone or update repository ───────────────────────────
if [ -z "$LOCAL_REPO" ]; then
    mkdir -p "$(dirname "$SRC_DIR")"
    if [ -d "$SRC_DIR/.git" ]; then
        echo ""
        echo "Updating existing installation..."
        git -C "$SRC_DIR" pull --ff-only
    else
        echo ""
        echo "Cloning from GitHub..."
        git clone "$REPO_URL" "$SRC_DIR"
    fi
    LOCAL_REPO="$SRC_DIR"
fi

# ── Create virtual environment ───────────────────────────
echo ""
echo "Creating virtual environment at $VENV_DIR ..."
"$PYTHON" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip

# ── Install QuickRun MCP ──────────────────────────────────
echo "Installing quickrun-mcp ..."
pip install --quiet "$LOCAL_REPO"

# ── Install data-analysis packages ───────────────────────
echo "Installing data-analysis packages (this may take a few minutes) ..."
pip install --quiet \
    pandas numpy openpyxl xlsxwriter python-docx python-pptx pypdf pdfplumber \
    matplotlib seaborn plotly kaleido reportlab Pillow lxml defusedxml markdown \
    mammoth imageio duckdb PyYAML requests \
    || echo "Warning: some packages failed — server still works."

# ── Create workspace ─────────────────────────────────────
mkdir -p "$WORKSPACE_DIR/artifacts" "$WORKSPACE_DIR/tmp"

# ── Self-test ────────────────────────────────────────────
echo ""
echo "Running self-test ..."
"$VENV_DIR/bin/quickrun-mcp" --help 2>/dev/null | head -1 || true
"$PYTHON" -c "
import sys; sys.path.insert(0,'$LOCAL_REPO/src')
from quickrun_mcp.config import Config
from quickrun_mcp.executor import StatelessExecutor
import asyncio
cfg = Config()
ex = StatelessExecutor(cfg)
result = asyncio.run(ex.execute('print(2+2)', timeout=10))
assert '4' in result, f'self-test failed: {result}'
print('  self-test passed: 2+2=4 ✓')
"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            Installation complete! ✓                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Copy the following into Quick > Customize > Connectors"
echo "  > Create > Local MCP / stdio:"
echo ""
echo "  ┌─ Command ──────────────────────────────────────────┐"
echo "  │  $VENV_DIR/bin/quickrun-mcp"
echo "  └────────────────────────────────────────────────────┘"
echo ""
echo "  ┌─ Args ─────────────────────────────────────────────┐"
echo "  │  (leave empty)                                       │"
echo "  └────────────────────────────────────────────────────┘"
echo ""
echo "  ┌─ Environment Variables ─────────────────────────────┐"
echo "  │  WORKSPACE_DIR    = $WORKSPACE_DIR"
echo "  │  ALLOWED_FOLDERS  = $HOME/Downloads:$HOME/Desktop"
echo "  │  DEFAULT_TIMEOUT  = 60"
echo "  │  MAX_OUTPUT_CHARS = 61440"
echo "  │  ALLOW_NETWORK    = true"
echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo "  TIP: Edit ALLOWED_FOLDERS to include the directories"
echo "  you want the agent to access on this machine."
echo ""
