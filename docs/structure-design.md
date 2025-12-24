# Claudex 结构设计（聚焦 Claude Code SDK + E2B）

本文基于当前项目代码实现说明运行位置、通信链路、产物持久化与多用户处理方式。

## 1. 组件与运行位置

- **Frontend**：React/Vite（容器内运行，服务端口 `3000`）。
- **Backend API**：FastAPI（容器内运行，服务端口 `8080`）。
- **PostgreSQL/Redis/Celery**：容器内运行（`docker-compose.yml`）。
- **E2B Sandbox**：远程托管运行，不在本仓库的 Docker Compose 中。
- **Claude Code CLI**：在 **两个位置** 均有安装：
  - E2B Sandbox 镜像（`e2b/e2b.Dockerfile` 第 50 行）
  - 后端容器（`backend/Dockerfile` 第 19 行）

## 2. Claude Code SDK 与 CLI 运行位置

### 2.1 核心概念区分

| 组件 | 定义 | 运行位置 |
|------|------|----------|
| **Claude Code SDK** (`ClaudeSDKClient`) | Python 客户端库，负责构建选项、管理连接、解析响应 | 后端容器 |
| **Claude Code CLI** (`claude`) | 实际执行 AI 对话的命令行工具 | 取决于 Transport |
| **Transport** | SDK 与 CLI 之间的通信层 | 决定 CLI 在哪里运行 |

### 2.2 两种运行模式

**模式 A：E2B Sandbox 内运行（主对话流）**

```
Backend Container                     E2B Sandbox (远程)
┌─────────────────────┐              ┌─────────────────────┐
│ ClaudeSDKClient     │              │                     │
│   ↓                 │   E2B API    │  claude CLI 进程    │
│ E2BSandboxTransport │ ◄──────────► │  (实际执行对话)     │
│   - connect()       │   stdin/out  │                     │
│   - write()         │   JSON Lines │  .claude/skills/    │
│   - read_messages() │              │  .claude/commands/  │
└─────────────────────┘              └─────────────────────┘
```

- 入口：`ClaudeAgentService.get_ai_stream()`
- Transport：`E2BSandboxTransport`（`backend/app/services/e2b_transport.py`）
- CLI 启动方式：`sandbox.commands.run("claude --output-format stream-json ...")`
- 通信协议：stdin/stdout 的 JSON Lines 流

**模式 B：后端容器内运行（辅助功能）**

```
Backend Container
┌─────────────────────┐
│ ClaudeSDKClient     │
│   ↓                 │
│ 默认 Transport      │
│   ↓                 │
│ claude CLI 进程     │
│ (本地子进程)        │
└─────────────────────┘
```

- 入口：`ClaudeAgentService.enhance_prompt()`
- Transport：SDK 默认的本地进程 Transport
- 用途：单轮 prompt 增强，无需 Sandbox 环境

### 2.3 为什么需要两种模式？

| 场景 | 选择模式 | 原因 |
|------|----------|------|
| 用户对话 | E2B Sandbox | 需要隔离的代码执行环境、文件系统持久化、用户资源隔离 |
| Prompt 增强 | 本地容器 | 单轮交互、无需文件系统、快速响应 |

## 3. Claude Code 与 E2B 的通信方式

### 3.1 运行链路（CLI 运行在 Sandbox）

1. Backend 从数据库拿到 `sandbox_id`，并从用户设置读取 `e2b_api_key`。
2. `E2BSandboxTransport.connect()` 调用 `AsyncSandbox.connect()` 连接到 E2B（`backend/app/services/e2b_transport.py`）。
3. 通过 `sandbox.commands.run()` 在 E2B 内启动 Claude CLI（后台进程）。
4. **通信方式**：通过标准输入/输出传输 **JSON Lines**。
   - Backend `send_stdin()` 写入 prompt。
   - 从 CLI stdout 读取 JSON（去掉 ANSI），解析成 SDK 事件流。

### 3.2 权限请求链路（MCP Permission Server）

E2B 内置 `permission_server.py`（MCP server），在需要权限时**反向调用**后端 API：

1. Sandbox 内 MCP server 向 `API_BASE_URL` 发送 HTTP 请求。
2. Backend 记录权限请求并等待用户确认。
3. MCP server 轮询获得批准/拒绝后返回给 Claude CLI。

相关位置：
- MCP server 启动配置：`backend/app/services/claude_agent.py` `_build_permission_server()`
- MCP 实现：`e2b/permission_server.py`
- 本地开发需外网访问（隧道）：`README.md` “Local Development with Permissions”

## 4. Claude Code 产物持久化方式

### 4.1 Sandbox 文件系统持久化（主路径）

Claude Code 生成的代码/产物默认写入 **E2B Sandbox 的 `/home/user`**。

持久化范围：
- **生命周期绑定到 Sandbox**：只要 `sandbox_id` 仍有效，文件一直存在。
- Sandbox 在聊天创建时生成并记录在 `chats.sandbox_id`（`backend/app/services/chat.py`，`backend/app/models/db_models/chat.py`）。
- 删除聊天时会调用 `delete_sandbox()` 清理（`backend/app/services/chat.py`）。

### 4.2 Checkpoint（消息级快照）

每次 assistant 消息完成后创建增量 checkpoint：

- `SandboxService.create_checkpoint()` 将 `/home/user` 以 rsync 增量方式保存到 `/home/user/.checkpoints/<message_id>`。
- checkpoint_id 保存到 `messages.checkpoint_id`（`backend/app/tasks/chat_processor.py`）。
- 可用于回退到指定消息（`restore_checkpoint()` / `restore_to_message()`）。

### 4.3 下载导出

支持将 Sandbox 文件打包下载：

- `generate_zip_download()` 打包 `/home/user` 文件并返回 zip（`backend/app/services/sandbox.py`）。
- API 提供下载入口（`backend/app/api/endpoints/sandbox.py`）。

### 4.4 附件存储（本地 + Sandbox 双写）

用户上传的附件会：

- 保存到后端本地 `storage/`（`backend/app/services/storage.py`）。
- 同时写入 Sandbox `/home/user` 供 Claude 使用（如果上传成功）。

> 结论：产物主存储在 E2B Sandbox，**没有自动同步回后端**；需要下载或额外同步流程。

## 5. 多用户处理与隔离

### 5.1 数据隔离

- User/Chat/Message 都与 `user_id` 绑定（`backend/app/models/db_models/user.py`、`chat.py`）。
- API 访问 Sandbox 前会校验 `sandbox_id` 是否属于当前用户（`backend/app/api/endpoints/sandbox.py`）。

### 5.2 运行隔离

- **每个聊天一个 Sandbox**（`ChatService.create_chat()` 创建并初始化）。
- 用户配置（API Key、GitHub Token、MCP/技能等）以 `UserSettings` 存储并加密（`EncryptedString`）。
- 自定义资源（skills/commands/agents）按用户复制到对应 Sandbox（`backend/app/services/sandbox.py`）。

### 5.3 并发与限额

- Celery 处理异步任务（`backend/app/tasks`）。
- 可配置每日消息额度（`User.daily_message_limit`）。

## 6. Custom Skills 管理方式

### 6.1 是否每个用户都可自定义

是。技能上传接口要求登录用户，技能元数据保存在该用户的 `UserSettings.custom_skills` 字段（JSON）。

相关入口：
- API：`POST /api/v1/skills/upload`（`backend/app/api/endpoints/skills.py`）
- UI：Settings -> Skills（`frontend/src/components/settings/tabs/SkillsSettingsTab.tsx`）

### 6.2 存储位置与结构

技能以 ZIP 文件形式落盘，路径按用户隔离：

- 基础目录：`settings.STORAGE_PATH`（默认 `/app/storage`）
- 技能目录：`/app/storage/skills/<user_id>/<skill_name>.zip`
  - 由 `SkillService` 创建（`backend/app/services/skill.py`）

### 6.3 校验与配额

上传时会校验：
- ZIP 必须包含唯一的 `SKILL.md`。
- `SKILL.md` 需包含 YAML frontmatter（`name`、`description`）。
- 名称会被清洗（小写、去非法字符、长度限制）。
- 每用户最大 10 个技能（`MAX_RESOURCES_PER_USER`）。
- 单个 ZIP 最大 100MB（`SkillService.MAX_SKILL_SIZE_BYTES`）。

### 6.4 注入到 Sandbox 的方式

当创建/初始化 Sandbox 时，后端会把启用的技能解压到 Sandbox：

- 目标路径：`/home/user/.claude/skills/<skill_name>/...`
- 由 `SandboxService._copy_all_resources_to_sandbox()` 统一打包上传并解压。

> 技能 ZIP 的"持久化"在后端 `/app/storage/skills/...`；进入 Sandbox 后的 `.claude/skills/` 是运行时副本。

## 7. 为什么需要将后端资源复制到 Sandbox？

### 7.1 核心原因：CLI 运行在 Sandbox 内

由于 Claude Code CLI **运行在 E2B Sandbox 内部**（而非后端容器），CLI 只能访问 Sandbox 的文件系统：

```
后端容器                              E2B Sandbox
┌─────────────────────┐              ┌─────────────────────┐
│ /app/storage/       │              │ /home/user/         │
│   skills/           │  ──复制──►   │   .claude/          │
│   commands/         │              │     skills/         │
│   agents/           │              │     commands/       │
│                     │              │     agents/         │
│ (CLI 无法访问)       │              │ (CLI 可以访问)       │
└─────────────────────┘              └─────────────────────┘
```

### 7.2 复制的资源类型

| 资源类型 | 后端存储位置 | Sandbox 目标位置 | 用途 |
|----------|--------------|------------------|------|
| Skills | `/app/storage/skills/<user_id>/` | `/home/user/.claude/skills/` | 扩展 Claude 能力的技能包 |
| Commands | `/app/storage/commands/<user_id>/` | `/home/user/.claude/commands/` | 自定义斜杠命令 |
| Agents | `/app/storage/agents/<user_id>/` | `/home/user/.claude/agents/` | 自定义 Agent 配置 |

### 7.3 复制时机与方式

- **时机**：Sandbox 初始化时（`SandboxService.initialize_sandbox()`）
- **方式**：`_copy_all_resources_to_sandbox()` 将所有启用的资源打包成 ZIP，通过 base64 编码上传到 Sandbox，然后解压
- **代码位置**：`backend/app/services/sandbox.py` 第 723-826 行

### 7.4 其他需要同步的配置

除了用户资源，还有环境变量和凭证需要注入到 Sandbox：

| 配置项 | 注入方式 | 用途 |
|--------|----------|------|
| `custom_env_vars` | 写入 `~/.bashrc` | 用户自定义环境变量 |
| `github_token` | 写入 `~/.bashrc` + `.git-askpass.sh` | Git 认证 |
| `openrouter_api_key` | 启动 `anthropic-bridge` 进程 | OpenRouter 模型代理 |

这些配置通过 `initialize_sandbox()` 中的并行任务完成（第 906-944 行）。

---

## 快速结论（回答问题）

- **Claude Code SDK 运行在哪里？** SDK (`ClaudeSDKClient`) 在后端容器中运行；CLI (`claude`) 在 E2B Sandbox 内运行（主对话流）或后端容器内运行（`enhance_prompt` 辅助功能）。
- **Claude Code 与 E2B 如何通信？** Backend 通过 E2B SDK 建立连接，在 Sandbox 内启动 CLI，通过 stdin/stdout 的 JSON Lines 双向流式通信；权限流通过 MCP server HTTP 回调后端。
- **产物如何持久化？** 生成代码写入 E2B Sandbox `/home/user`，可通过 checkpoint 与 zip 下载持久化；删除聊天会删除 Sandbox。
- **多用户如何处理？** 每个用户/聊天绑定独立 Sandbox 和数据库记录；API 通过 `user_id` 进行访问校验与隔离，用户设置独立存储并用于 Sandbox 初始化。
- **Custom Skills 如何管理？** 每个用户可上传 ZIP 技能包，元数据存 `UserSettings.custom_skills`，文件落盘到 `/app/storage/skills/<user_id>/`，初始化 Sandbox 时复制到 `.claude/skills/`。
- **为什么需要复制资源到 Sandbox？** 因为 Claude Code CLI 运行在 E2B Sandbox 内，无法直接访问后端容器的文件系统，必须在 Sandbox 初始化时将用户资源（skills/commands/agents）和配置（环境变量/凭证）复制或注入到 Sandbox 的 `/home/user` 目录。
