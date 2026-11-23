# QuickRun MCP

> **给 AWS Quick 补上 Code Execution / Local Code Execution / Shell 的本地 MCP 连接器**
> Python & shell code-execution MCP server for AWS Quick (and any MCP client).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)

---

## ⚠️ 访问权限 / Access

**本仓库为私有仓库。** 您需要先联系仓库作者，被加为 Collaborator，然后完成以下步骤才能访问：

```bash
# 1. 安装/登录 GitHub CLI（如未安装：brew install gh）
gh auth login

# 2. 配置 git 使用 gh 凭证（让 git clone/pull/uvx 能访问私有仓库）
gh auth setup-git
```

---

## English Quick Start

```bash
# Method A: zero-install with uvx (requires gh auth login + gh auth setup-git)
# In Quick: Command=uvx  Args=(see below)  Env=(see below)

# Method B: one-command install
gh repo clone liangyimingcom/quickrun-mcp ~/.quickrun/src && \
  bash ~/.quickrun/src/install.sh
```

After install, fill in Quick connectors with the **Command / Args / Env** printed at
the end of `install.sh`.

> **Windows 用户**：请直接看 [第 11 节：Windows 完整安装实践](#11-windows-完整安装实践quickrun-mcp)；
> 装好 QuickRun 后，可按 [第 12 节](#12-引导在-windows-上安装-mcp-hub) 继续安装 mcp-hub。

---

## 1. QuickRun 是什么？解决什么问题？

AWS Quick 在某些部署下缺少 **Code Execution** 和 **Local Code Execution** 系统工具。
QuickRun 是一个本地 MCP 连接器，通过 stdio 接入 Quick，补全这两类工具，并额外提供
与主流 shell-runner MCP 完全兼容的 `run_command` / `run_script` / `list_processes`。

### 功能对照表（10 个工具）

| 工具 | 类型 | 说明 |
|---|---|---|
| `run_python` | Python 持久会话 | 变量/函数跨调用保留，workspace 可写 |
| `run_python_with_write` | Python 持久会话 | 同上，另允许写入 ALLOWED_FOLDERS |
| `run_python_on_device` | Python 无状态 | 每次新进程，本地大文件读取 |
| `run_python_on_device_with_write` | Python 无状态 | 同上，另允许写入 ALLOWED_FOLDERS |
| `reset_python_session` | 管理 | 重置持久 worker，清空所有变量 |
| `run_command` | Shell | 单条命令，兼容 shell-runner MCP |
| `run_script` | Shell | 多行 bash 脚本，兼容 shell-runner MCP（Windows 需 Git Bash） |
| `list_processes` | Shell (只读) | ps aux（Windows 为 tasklist），可按名称过滤 |
| `list_allowed_folders` | 只读 | 列出可访问目录 |
| `list_installed_packages` | 只读 | pip list |

---

## 2. 前置条件

| 条件 | macOS | Linux | Windows |
|---|---|---|---|
| Quick 桌面端在线 | ✅ 必须 | ✅ 必须 | ✅ 必须 |
| Python 3.10+ | 推荐 (方式 B) | 推荐 (方式 B) | 推荐 (方式 B) |
| uv | 方式 A 必须 | 方式 A 必须 | 方式 A 必须 |
| GitHub CLI (gh) | 私有仓库必须 | 私有仓库必须 | 私有仓库必须 |
| sandbox-exec | 自带 | ❌ 用软沙箱 | ❌ 用软沙箱 |
| bash（shell 工具） | 自带 | 自带 | Git for Windows 自带的 Git Bash（自动查找） |

**安装 uv（如未安装）：**
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或: brew install uv

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**安装并登录 GitHub CLI（私有仓库访问）：**
```bash
brew install gh        # macOS
# apt install gh       # Ubuntu
gh auth login          # 按提示选择 GitHub.com → HTTPS → 粘贴 token
gh auth setup-git      # 让 git/uvx 通过 gh 凭证访问私有仓库
```

---

## 3. 安装

### 方式 A：uvx 零安装（推荐，自动下载最新版）

无需 clone 仓库，uv 会自动从 GitHub 拉取代码并按需安装依赖。

**前提：** 已完成 `gh auth login` + `gh auth setup-git`。

在 Quick 桌面端配置连接器（详见第 7 节）：

| 字段 | 填写内容 |
|---|---|
| **Command** | `/opt/homebrew/bin/uvx`（或 `~/.local/bin/uvx`，运行 `which uvx` 确认） |
| **Args（每项分开填）** | `--from` `quickrun-mcp[data] @ git+https://github.com/liangyimingcom/quickrun-mcp` `quickrun-mcp` |
| **Env** | 见第 4 节 |

> **SSH 备选（如 HTTPS 有问题）：**
> Args: `--from` `quickrun-mcp[data] @ git+ssh://git@github.com/liangyimingcom/quickrun-mcp` `quickrun-mcp`
> 需先配置 SSH key：`ssh-keygen -t ed25519` → 添加到 GitHub Settings → SSH keys。

`[data]` 额外项自动安装 pandas、numpy、openpyxl、matplotlib、Pillow、requests 等数据分析包。

### 方式 B：一键脚本安装

```bash
# 第一次安装（需要 GitHub CLI 访问私有仓库）
gh repo clone liangyimingcom/quickrun-mcp ~/.quickrun/src && \
  bash ~/.quickrun/src/install.sh

# 升级（已安装后）
bash ~/.quickrun/src/install.sh   # 脚本自动 git pull 再重装
```

脚本完成后会打印要填入 Quick 的 **Command / Args / Env** 原值。

---

## 4. Env 变量说明

| 变量 | 说明 | 默认值 |
|---|---|---|
| `WORKSPACE_DIR` | 代码执行的工作目录（workspace），始终可写 | `~/.quickrun/workspace` |
| `ALLOWED_FOLDERS` | 额外允许访问的目录，冒号分隔（Windows 用分号） | 空 |
| `DEFAULT_TIMEOUT` | 默认超时（秒） | `60` |
| `MAX_OUTPUT_CHARS` | 输出截断上限（字节） | `61440`（60 KB） |
| `ALLOW_NETWORK` | 代码是否可访问网络 | `true` |
| `ENABLE_SHELL_TOOLS` | 是否暴露 run_command/run_script/list_processes | `true` |
| `SHELL_ALLOW_SUDO` | shell 命令是否允许 sudo | `false` |
| `SHELL_SANDBOX` | 是否对 shell 命令启用 sandbox-exec（macOS） | `false` |
| `QUICKRUN_BASH` | shell 工具使用的 bash 完整路径；不填则自动查找（Windows 上找 Git Bash） | 自动 |

**ALLOWED_FOLDERS 示例：**
```
# macOS / Linux：冒号分隔
ALLOWED_FOLDERS = /Users/yourname/Downloads:/Users/yourname/Projects/data

# Windows：分号分隔  
ALLOWED_FOLDERS = C:\Users\yourname\Downloads;C:\Users\yourname\data
```

> **安全提示：** `ALLOWED_FOLDERS` 中的目录，代码（通过 `*_with_write` 工具）可以读写。
> **不要**把包含 SSH 私钥、云凭证等的目录加入 ALLOWED_FOLDERS。

---

## 5. 在 Quick 中配置连接器（详细步骤）

1. 打开 AWS Quick 桌面端，确保处于**在线**状态
2. 点击右上角 **Customize**（齿轮/设置图标）
3. 选择 **Connectors** → **Create**
4. 类型选择 **本地连接器（Local MCP / stdio）**
5. 填写：
   - **Name**：`QuickRun`（或你喜欢的名字）
   - **Command**：（见上方方式 A 或方式 B 的值）
   - **Args**：（见上方方式 A，每项单独填写）
   - **Env**：（逐行填入 WORKSPACE_DIR、ALLOWED_FOLDERS 等）
6. 点击**保存**
7. macOS 可能弹出"是否允许 Quick 运行此程序"的系统对话框 → 点击**允许**
8. 在连接器列表中找到 QuickRun → 打开右侧**开关**

---

## 6. 首次验证

连接器启用后，在 Quick Chat 发送以下 3 条消息验证功能：

```
1. 请用 Python 计算 sum(range(1, 101)) 并输出结果。
   （预期：5050）

2. 请用 Python 列出 WORKSPACE_DIR 下的文件（os.listdir）。
   （预期：显示 artifacts/ tmp/ 等目录）

3. 请用 run_command 执行 echo "QuickRun OK"。
   （预期：stdout 包含 "QuickRun OK"，return_code=0）
```

---

## 7. 升级 / 卸载

```bash
# 升级（方式 B）
bash ~/.quickrun/src/install.sh    # git pull + reinstall

# 升级（方式 A）：uvx 会缓存已经下载的版本。如果启动的还是旧版本，执行一次带 --refresh 的命令，
# 然后在 Quick 里把连接器关掉再打开：
uvx --refresh --from "quickrun-mcp[data] @ git+https://github.com/liangyimingcom/quickrun-mcp" quickrun-mcp --help

# 卸载
rm -rf ~/.quickrun
# 然后在 Quick Customize → Connectors 中删除连接器
```

---

## 8. 安全模型与限制

请阅读 [SECURITY.md](SECURITY.md) 了解完整安全说明。

**关键限制：**
- 代码在**本机**运行，不是远端沙箱，请仅授权可信的 AI 助手使用
- macOS 使用 `sandbox-exec` 硬沙箱；Linux/Windows 使用软沙箱（`sys.addaudithook`）
- 持久会话（`run_python`）超时后**所有变量丢失**，需重新初始化数据
- shell 工具无文件系统沙箱（默认），这是有意设计，方便调用系统工具

---

## 9. 常见问题排查

**Q: `uvx: command not found`**
安装 uv：`curl -LsSf https://astral.sh/uv/install.sh | sh`，然后确认 Command 填写 `which uvx` 的完整路径。

**Q: `gh: authentication required` / 私有仓库克隆失败**
运行 `gh auth login` 和 `gh auth setup-git`，确认 `gh auth status` 显示已登录。

**Q: `sandbox-exec` 报错**
检查 `/tmp` 是否可写。若报 "unbound variable" 类错误，可在 GitHub Issues 提交。

**Q: 超时**
`run_python` / `run_python_with_write` 的 timeout 上限是 `DEFAULT_TIMEOUT`（默认 60 秒），传更大的值也会被截到这个上限。
构建、跑测试这类长任务，用 `run_python_on_device(_with_write)`（最大 270 秒），或者增大 `DEFAULT_TIMEOUT`。

**Q: 缺少某个 Python 包**
```bash
# 方式 B（venv 安装）
source ~/.quickrun/venv/bin/activate
pip install <package>

# 方式 A（uvx）：在 Args 中追加 --with <package>
```

**Q: `run_command` 被拦截**
检查命令是否匹配 `DANGEROUS_PATTERNS`。若需要 sudo，设 `SHELL_ALLOW_SUDO=true`。

---

## 10. 与 Quick 内置工具同时存在时的说明

如果您的 Quick 实例**同时**有内置 Code Execution 工具和 QuickRun 连接器：
- 工具名冲突时 AI 可能混用两者
- **建议**：在 Quick 设置中只启用其中一个
- QuickRun 的 `run_command` / `run_script` / `list_processes` 与常见 shell-runner MCP
  服务（同名工具）**兼容**，可直接替换使用

---

## 11. Windows 完整安装实践（quickrun-mcp）

以下步骤在 **Windows Server 2025 + PowerShell 5.1 + Git for Windows 2.56** 上实际跑通，Windows 10/11 同样适用。
全程用 **方式 A（uvx）**：uv 会自己下载 Python 和依赖，**不需要**另外安装 Python。

### 11.1 准备

| 需要 | 检查命令（PowerShell） | 说明 |
|---|---|---|
| AWS Quick 桌面版 | — | 保持在线 |
| Git for Windows | `git --version` | 自带 **Git Bash**，`run_command` / `run_script` 会自动找到它 |
| uv | `& "$env:USERPROFILE\.local\bin\uvx.exe" --version` | 没有就按 11.2 安装 |
| GitHub 访问 | — | 仓库是私有时，需要 `gh auth login` + `gh auth setup-git`（见文首「访问权限」） |

### 11.2 安装 uv

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

装完**关掉 PowerShell 再重新打开**，让 PATH 生效。

> 如果报 `The process cannot access the file '...\.local\bin\uv.exe' because it is being used by another process`，
> 说明 uv **已经装过而且正在运行**（比如已有别的连接器在用 uvx）。先确认能不能用：
> ```powershell
> & "$env:USERPROFILE\.local\bin\uvx.exe" --version
> ```
> 能输出版本号就跳过重装。确实要重装，先结束占用的进程（会断开正在用 uv 的连接器，装完在 Quick 里把它关掉再打开即可）：
> ```powershell
> Get-Process uv, uvx -ErrorAction SilentlyContinue | Stop-Process -Force
> ```

### 11.3 先在命令行试跑一次

```powershell
& "$env:USERPROFILE\.local\bin\uvx.exe" --from "quickrun-mcp[data] @ git+https://github.com/liangyimingcom/quickrun-mcp" quickrun-mcp --help
```

第一次会下载 Python 和数据分析包，需要一两分钟。报认证错误就是仓库访问权限的问题，先完成 `gh auth login` + `gh auth setup-git`。

### 11.4 在 Quick 里添加连接器

Customize → Connectors → Create → 本地连接器（Local MCP）。可以直接参照下面的 JSON 填写
（把 `<用户名>` 换成你的 Windows 用户名；JSON 里的反斜杠要写成两个 `\\`）：

```json
{
  "mcpServers": {
    "quickrun": {
      "command": "C:\\Users\\<用户名>\\.local\\bin\\uvx.exe",
      "args": [
        "--from",
        "quickrun-mcp[data] @ git+https://github.com/liangyimingcom/quickrun-mcp",
        "quickrun-mcp"
      ],
      "env": {
        "WORKSPACE_DIR": "C:\\Users\\<用户名>\\.quickrun\\workspace",
        "ALLOWED_FOLDERS": "C:\\Users\\<用户名>\\quick-mcp-hub"
      }
    }
  }
}
```

不想手动改路径，可以在 PowerShell 里生成这段 JSON 并复制到剪贴板：

```powershell
$cfg = @{ mcpServers = @{ quickrun = @{
  command = "$env:USERPROFILE\.local\bin\uvx.exe"
  args    = @("--from","quickrun-mcp[data] @ git+https://github.com/liangyimingcom/quickrun-mcp","quickrun-mcp")
  env     = @{ WORKSPACE_DIR = "$env:USERPROFILE\.quickrun\workspace"; ALLOWED_FOLDERS = "$env:USERPROFILE\quick-mcp-hub" }
}}}
$cfg | ConvertTo-Json -Depth 5 | Tee-Object -Variable j; $j | Set-Clipboard
```

要点：

- `ALLOWED_FOLDERS` 多个目录用**分号 `;`** 分隔，例如 `C:\Users\me\data;D:\work`。
- 逐项填写时：`command` → Command；`args` 的 3 项**分 3 行**填进 Args；`env` 的每一项填进 Env。
- 保存后打开连接器开关。

### 11.5 验证

在 Quick 里依次说：

1. 「列出 QuickRun 允许访问的目录」：每个目录**完整地占一行**（例如 `C:\Users\me\quick-mcp-hub`）。
2. 「用 Python 计算 sum(range(1, 101))」：结果是 5050。
3. 「用 run_command 执行 `git --version`」：`return_code=0`。

### 11.6 Windows 使用提示

- **长任务**（构建、跑测试）：`run_python` 最多 `DEFAULT_TIMEOUT` 秒（默认 60）。用 `run_python_on_device_with_write`（最多 270 秒），
  或者调大 `DEFAULT_TIMEOUT`。
- **子进程输出**：代码里启动的子进程，如果没有指定 stdout，它的输出会被丢弃（不会再混进协议）。要看输出请用
  `subprocess.run(..., capture_output=True, text=True)`。
- **后台任务**：可以用 `subprocess.Popen(...)` 启动后台进程，把输出重定向到文件，之后读文件看进度。
- **shell 工具**：`run_command` / `run_script` 用 Git Bash 执行（`pwd` 输出 `/c/Users/...` 形式，`pwd -W` 输出 `C:/Users/...`）。
  没有 Git Bash 时，`run_command` 改用 `cmd.exe`，`run_script` 会提示安装 Git for Windows 或设置 `QUICKRUN_BASH`。

### 11.7 v1.1.0 修复的 Windows 问题

v1.0.0 在 Windows 上有下面这些问题，v1.1.0 都已修复，并加了回归测试 `tests/test_windows_compat.py`
（Windows 上 64 个测试通过、5 个仅 macOS 的跳过）：

| 现象（v1.0.0） | 原因 | 修复 |
|---|---|---|
| `list_allowed_folders` 把 `C:\Users\me\x` 显示成 `C` 和 `\Users\me\x` 两项 | `ALLOWED_FOLDERS` 以及传给 worker 的路径列表一律按 `:` 拆分 | 改按 `os.pathsep` 拆分（Windows 为 `;`） |
| `run_command` / `run_script` 报 `[WinError 2]` | 写死了 `bash`，PATH 里没有 | 自动查找 Git Bash，可用 `QUICKRUN_BASH` 指定；`run_command` 找不到 bash 时改用 `cmd.exe` |
| `list_processes` 报错 | 调用 `ps aux` | Windows 改用 `tasklist` |
| 超时、`reset_python_session` 直接报 `Error executing tool` | Windows 没有 `os.getpgid` / `os.killpg`，结束进程时抛异常 | 用 `taskkill /T /F` 结束进程树，任何平台都不会抛异常 |
| **结果晚一轮**：拿到的是上一次调用的输出 | 上一条在超时或被客户端取消后，worker 没被结束，晚到的结果被下一次调用读走 | 每个请求带 id，只接受 id 匹配的回复；请求被取消时立刻结束 worker |
| **后台进程卡住**：`Popen` 起的进程不动，直到下一次调用才继续 | 子进程继承了 worker 的 stdin 管道；Windows 上 worker 在该管道上有未完成的同步读时，子进程启动会卡住 | worker 把协议管道复制成私有句柄，fd 0/1/2 指向空设备，子进程不再继承管道 |

## 12. 引导：在 Windows 上安装 mcp-hub

[mcp-hub](https://github.com/nimysan/quick-mcp-hub) 是一个本地 MCP 连接器，让 Quick 以你本人的身份访问
邮箱、飞书、GitHub、Jira 等系统，也能只读访问本机 Outlook 邮件。以下步骤在 Windows 上实际跑通
（分支 `feat/merge-localmail-feishu`，Go 1.27.4，`go vet` 和 `go test` 全部通过）。

> **捷径**：装好 QuickRun 后，可以直接对 Quick 说「按 quickrun-mcp README 第 12 节，在我的 Windows 上安装 mcp-hub」，
> 由 Quick 通过 QuickRun 执行下面的命令。请先把 `C:\Users\<用户名>\quick-mcp-hub` 加进 QuickRun 的 `ALLOWED_FOLDERS`。

### 12.1 准备

| 需要 | 检查命令 |
|---|---|
| Go 1.26.4 或更高 | `go version` |
| Git | `git --version` |
| AWS Quick 桌面版 | — |

mcp-hub 文档里的 `plugins/build.sh` 和 `make build` 要用 bash 和 make，Windows 默认没有 make。
下面用 **PowerShell 原生命令**完成同样的构建，不需要 bash 和 make。

### 12.2 拉代码并构建

```powershell
cd $env:USERPROFILE
git clone https://github.com/nimysan/quick-mcp-hub.git
cd quick-mcp-hub
git checkout feat/merge-localmail-feishu      # 合并进 main 之后改用 main

# 可选：proxy.golang.org 访问不了时用国内镜像（与 Makefile 默认一致）
# $env:GOPROXY = "https://goproxy.cn,direct"; $env:GOSUMDB = "sum.golang.google.cn"

# 1) 构建 wasm 插件（等价于 plugins/build.sh）
New-Item -ItemType Directory -Force plugins\dist\ghwasm | Out-Null
$env:GOOS = "wasip1"; $env:GOARCH = "wasm"
go build -buildmode=c-shared -o plugins\dist\ghwasm\ghwasm.wasm .\plugins\ghwasm
Remove-Item Env:GOOS, Env:GOARCH
Copy-Item plugins\ghwasm\manifest.json plugins\dist\ghwasm\

# 2) 构建主程序（等价于 make build）
$env:CGO_ENABLED = "0"
go build -trimpath -ldflags "-s -w -X main.version=0.1.0" -o dist\mcp-hub.exe .

# 3) 验证
dist\mcp-hub.exe -h
```

第一次构建要下载依赖，需要几分钟。产物：`plugins\dist\ghwasm\ghwasm.wasm`（约 4.5 MB）、`dist\mcp-hub.exe`（约 20 MB）。

可选，跑测试（先完成第 1 步构建插件，否则 wasm 插件相关的测试会失败）：

```powershell
go vet ./...
go test -count=1 ./...      # 参考：约 30 秒，21 个包 ok、5 个包没有测试文件
```

### 12.3 配置渠道

```powershell
dist\mcp-hub.exe -ui
```

会弹出配置窗口 http://127.0.0.1:7801（只监听本机）。

1. 至少添加一个渠道，点「测试并保存」。渠道保存在 `%APPDATA%\mcp-hub\channels.json`，凭据存进 **Windows 凭据管理器**。
2. **本机邮件（只读，不需要密码）**：在「内置渠道」里添加，勾选来源：
   - **新版 Outlook**：只能读离线缓存里的邮件（默认最近 30 天、离线设置里选中的文件夹）。
   - **经典版 Outlook（PST/OST）**：读之前要完全退出 Outlook（任务管理器里没有 `OUTLOOK.EXE`）。
3. 写操作（发信、建 Issue 等）默认关闭，需要时在「权限与工具」里打开。
4. 配完关掉窗口，结束后台的配置进程。**不要**用 `taskkill /IM mcp-hub.exe`，它会把 Quick 正在用的 `-serve` 进程一起结束：

```powershell
Get-CimInstance Win32_Process -Filter "Name='mcp-hub.exe'" |
  Where-Object CommandLine -match '-ui' |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### 12.4 接入 Quick

Customize → Connectors → Create → Add MCP → Local：

```json
{
  "mcpServers": {
    "mcp-hub": {
      "command": "C:\\Users\\<用户名>\\quick-mcp-hub\\dist\\mcp-hub.exe",
      "args": ["-serve"]
    }
  }
}
```

逐项填写时：Command 填 `mcp-hub.exe` 的**完整路径**，Arguments 只填 `-serve`（不加引号）。点 Test connection。

### 12.5 验证

在 Quick 里试：

- 「列一下我本机邮件的文件夹」：返回收件箱、已发送等文件夹和封数（`total` 是本地缓存的封数）。
- 「看看收件箱最新 5 封邮件」，再「读一下第一封」：中文主题、HTML 正文（转成纯文本）、附件文件名都能读到，读取不会把邮件标成已读。

### 12.6 常见问题

| 现象 | 处理 |
|---|---|
| Quick 显示连接失败 | 至少配一个渠道；Command 用完整路径 |
| 改了配置或重新构建，工具没变 | 在 Quick 里把 connector 关掉再打开 |
| `plugins/build.sh` / `make` 跑不了 | 用 12.2 的 PowerShell 命令；或在 Git Bash 里跑 `plugins/build.sh`，再用 `go build` 代替 `make build` |
| `go test` 有一批 wasm 用例失败 | 先完成 12.2 第 1 步构建插件 |
| 本机邮件文件夹大多显示 0 封 | 新版 Outlook 只缓存最近 30 天和离线设置里选中的文件夹 |
| 经典版 Outlook 提示文件被占用 | 完全退出 Outlook 再试 |
| 首次运行被 SmartScreen 拦 | 选「仍要运行」；程序未签名 |

---

## 与常见 shell-runner MCP 的兼容性

QuickRun 的 shell 工具与常见 shell-runner MCP 服务工具同名（`run_command` / `run_script` / `list_processes`），返回格式兼容（`{stdout, stderr, return_code}`，另加 `truncated` 和 `duration_ms`）。

相比典型参考实现的改进：
- 超时时正确结束整个进程树（macOS/Linux 用 killpg，Windows 用 `taskkill /T /F`），不会留下孤儿进程
- 输出按 `MAX_OUTPUT_CHARS` 自动截断（头尾保留）
- 扩展的危险命令拦截列表（新增 `rm -rf ~`、`curl|sh`、`wget|sh` 等）
- 可选 `SHELL_SANDBOX=true` 对 shell 命令启用 macOS sandbox-exec

---

## mcp-config.example.json

参见 [mcp-config.example.json](mcp-config.example.json)。

---

## Contributing / License

MIT License — 欢迎提交 Issues 和 Pull Requests。
