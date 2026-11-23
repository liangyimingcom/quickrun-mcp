# QuickRun MCP installer for Windows
# Usage: .\install.ps1
# Requires: gh auth login (for private repo access)
param(
    [string]$InstallBase = "$env:USERPROFILE\.quickrun",
    [string]$RepoUrl    = "https://github.com/liangyimingcom/quickrun-mcp"
)
$ErrorActionPreference = "Stop"

$SrcDir       = "$InstallBase\src\quickrun-mcp"
$VenvDir      = "$InstallBase\venv"
$WorkspaceDir = "$InstallBase\workspace"

Write-Host "QuickRun MCP Installer (Windows)" -ForegroundColor Cyan
Write-Host "Install dir : $InstallBase"
Write-Host "Workspace   : $WorkspaceDir"

# --- Python ---
$python = $null
foreach ($c in @("python", "python3", "py")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $python = $c; break }
}
if (-not $python) { Write-Error "Python 3.10+ not found."; exit 1 }
$pyVer = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "Python      : $python ($pyVer)"

# --- Clone or update repo ---
if (-not (Test-Path "$SrcDir\.git")) {
    Write-Host "Cloning from GitHub..."
    & git clone $RepoUrl $SrcDir
} else {
    Write-Host "Updating existing installation..."
    & git -C $SrcDir pull --ff-only
}

# --- Venv ---
Write-Host "Creating virtual environment..."
& $python -m venv $VenvDir
$pip   = "$VenvDir\Scripts\pip.exe"
$entry = "$VenvDir\Scripts\quickrun-mcp.exe"

& $pip install --quiet --upgrade pip
& $pip install --quiet $SrcDir
Write-Host "Installing data packages..."
try {
    & $pip install --quiet pandas numpy openpyxl matplotlib Pillow requests PyYAML duckdb pdfplumber python-docx python-pptx
} catch { Write-Warning "Some data packages failed; server still works." }

# --- Workspace ---
New-Item -ItemType Directory -Force -Path "$WorkspaceDir\artifacts" | Out-Null
New-Item -ItemType Directory -Force -Path "$WorkspaceDir\tmp"       | Out-Null

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Command  : $entry"
Write-Host "Args     : (leave empty)"
Write-Host ""
Write-Host "Environment Variables:"
Write-Host "  WORKSPACE_DIR    = $WorkspaceDir"
Write-Host "  ALLOWED_FOLDERS  = $env:USERPROFILE\Downloads;$env:USERPROFILE\Desktop"
Write-Host "  DEFAULT_TIMEOUT  = 60"
Write-Host "  MAX_OUTPUT_CHARS = 61440"
Write-Host "  ALLOW_NETWORK    = true"
