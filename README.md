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
| `run_script` | Shell | 多行 bash 脚本，兼容 shell-runner MCP |
| `list_processes` | Shell (只读) | ps aux，可按名称过滤 |
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
| **Args（每项分开填）** | `--from` `git+https://github.com/liangyimingcom/quickrun-mcp` `quickrun-mcp[data]` |
| **Env** | 见第 4 节 |

> **SSH 备选（如 HTTPS 有问题）：**
> Args: `--from` `git+ssh://git@github.com/liangyimingcom/quickrun-mcp` `quickrun-mcp[data]`
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

# 升级（方式 A）：uvx 每次启动时自动拉取最新，无需手动操作

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
增大 `DEFAULT_TIMEOUT`（秒）。`run_python_on_device` 类工具最大支持 270 秒。

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

## 与常见 shell-runner MCP 的兼容性

QuickRun 的 shell 工具与常见 shell-runner MCP 服务工具同名（`run_command` / `run_script` / `list_processes`），返回格式兼容（`{stdout, stderr, return_code}`，另加 `truncated` 和 `duration_ms`）。

相比典型参考实现的改进：
- 超时时正确 killpg 整个进程组（含子进程），不会留下孤儿进程
- 输出按 `MAX_OUTPUT_CHARS` 自动截断（头尾保留）
- 扩展的危险命令拦截列表（新增 `rm -rf ~`、`curl|sh`、`wget|sh` 等）
- 可选 `SHELL_SANDBOX=true` 对 shell 命令启用 macOS sandbox-exec

---

## mcp-config.example.json

参见 [mcp-config.example.json](mcp-config.example.json)。

---

## Contributing / License

MIT License — 欢迎提交 Issues 和 Pull Requests。
