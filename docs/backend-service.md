# Backend 服务架构详解

## 1. 概述

Backend 服务是整个系统的核心编排层，负责将单用户的 Claude CLI 工具转变为多用户的 Web 应用服务。它不直接执行 AI 推理，而是协调 Claude Agent SDK、E2B 沙箱和 Claude CLI 之间的交互。

## 2. Backend 主要承载的功能

### 2.1 功能全景图

```mermaid
graph TB
    subgraph "Backend 核心职责"
        AUTH[用户认证与授权]
        MULTI[多用户隔离]
        PERSIST[数据持久化]
        STREAM[实时流式传输]
        ORCH[服务编排]
    end

    subgraph "业务功能"
        CHAT[聊天管理]
        MSG[消息处理]
        FILE[文件上传]
        PERM[权限审批]
        CHECKPOINT[状态检查点]
    end

    subgraph "集成功能"
        SDK_INT[SDK 集成]
        E2B_INT[E2B 沙箱管理]
        CLI_INT[CLI 进程控制]
        MCP_INT[MCP 服务器配置]
    end

    AUTH --> CHAT
    MULTI --> CHAT
    PERSIST --> MSG
    STREAM --> MSG
    ORCH --> SDK_INT
    ORCH --> E2B_INT
    ORCH --> CLI_INT
```

### 2.2 功能分类详解

| 功能类别 | 具体功能 | 说明 |
|----------|----------|------|
| **用户管理** | 认证、授权、会话 | JWT Token、OAuth 集成 |
| **聊天管理** | 创建、列表、删除、归档 | 多用户聊天隔离 |
| **消息处理** | 发送、接收、流式输出 | SSE 实时推送 |
| **沙箱管理** | 创建、连接、销毁 | E2B 沙箱生命周期 |
| **文件处理** | 上传、同步、下载 | 沙箱内文件操作 |
| **权限控制** | 工具审批、危险操作确认 | Permission Server |
| **状态管理** | 检查点、恢复、会话续传 | 增量备份 |
| **配置管理** | 环境变量、MCP、模型选择 | 用户自定义配置 |

### 2.3 Backend 独有能力（CLI 不具备）

```mermaid
graph LR
    subgraph "Backend 独有"
        B1[多用户隔离]
        B2[数据库持久化]
        B3[Redis 流式分发]
        B4[Celery 异步任务]
        B5[Token 用量追踪]
        B6[成本核算]
        B7[检查点管理]
        B8[文件附件处理]
    end

    subgraph "CLI 已有"
        C1[AI 推理]
        C2[工具执行]
        C3[文件操作]
        C4[会话管理]
    end

    B1 -.->|增强| C4
    B8 -.->|预处理| C3
```

## 3. 为什么需要 Claude Agent SDK

### 3.1 SDK 的角色

Claude Agent SDK 是 Anthropic 官方提供的 Python 库，用于与 Claude CLI 进行程序化交互。

```mermaid
graph TB
    subgraph "没有 SDK 的情况"
        APP1[应用代码]
        PROC1[subprocess.Popen]
        CLI1[Claude CLI]

        APP1 -->|手动解析 stdout| PROC1
        PROC1 -->|原始字节流| CLI1
    end

    subgraph "使用 SDK 的情况"
        APP2[应用代码]
        SDK2[Claude Agent SDK]
        TRANS2[Transport 接口]
        CLI2[Claude CLI]

        APP2 -->|类型化 API| SDK2
        SDK2 -->|标准协议| TRANS2
        TRANS2 -->|stream-json| CLI2
    end

    style SDK2 fill:#9f9
```

### 3.2 SDK 提供的核心能力

```python
# SDK 提供的类型化接口
from claude_agent_sdk import (
    ClaudeAgentOptions,    # 配置对象，30+ 参数
    ClaudeSDKClient,       # 异步客户端
    ResultMessage,         # 响应消息类型
    UserMessage,           # 用户消息类型
    TextBlock,             # 文本内容块
    ToolUseBlock,          # 工具调用块
    ThinkingBlock,         # 扩展思考块
)
```

### 3.3 SDK vs 直接调用 CLI

| 方面 | 使用 SDK | 直接调用 CLI |
|------|----------|--------------|
| **类型安全** | 完整的类型定义 | 需要手动解析 JSON |
| **错误处理** | 结构化异常 | 需要解析 stderr |
| **协议兼容** | 自动适配版本 | 需要跟踪协议变化 |
| **消息解析** | 自动解析内容块 | 手动解析 JSON 结构 |
| **会话管理** | 内置 resume 支持 | 需要手动管理 |
| **维护成本** | 低（官方维护） | 高（自行维护） |

### 3.4 SDK 在项目中的使用

```python
# 实际使用示例 - claude_agent.py
async def get_ai_stream(self, ...):
    options = ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code"},
        permission_mode="auto",
        model="claude-opus-4-5",
        mcp_servers=mcp_config,
        resume=session_id,
    )

    async with ClaudeSDKClient(transport, options) as client:
        async for message in client.receive_response():
            # message 是类型化的 ResultMessage
            for block in message.content:
                if isinstance(block, TextBlock):
                    yield text_event(block.text)
                elif isinstance(block, ToolUseBlock):
                    yield tool_started_event(block)
```

## 4. 为什么还需要 Claude CLI

### 4.1 CLI 的角色

Claude CLI 是实际执行 AI 推理和工具调用的二进制程序。SDK 只是与它通信的协议层，真正的"大脑"是 CLI。

```mermaid
sequenceDiagram
    participant Backend as Backend Service
    participant SDK as Claude Agent SDK
    participant Transport as E2BSandboxTransport
    participant Sandbox as E2B Sandbox
    participant CLI as Claude CLI

    Note over Backend,CLI: SDK 不执行 AI 推理，只是协议桥接

    Backend->>SDK: 发送用户消息
    SDK->>Transport: 序列化为 stream-json
    Transport->>Sandbox: WebSocket 传输
    Sandbox->>CLI: stdin 写入

    Note over CLI: CLI 执行 AI 推理<br/>调用工具<br/>读写文件

    CLI-->>Sandbox: stdout 输出
    Sandbox-->>Transport: WebSocket 返回
    Transport-->>SDK: 解析 JSON
    SDK-->>Backend: 类型化消息
```

### 4.2 CLI 独有能力

```mermaid
graph TB
    subgraph "Claude CLI 核心能力"
        AI[AI 推理引擎]
        TOOLS[工具执行]
        FS[文件系统访问]
        MCP[MCP 服务器]
        SESSION[会话状态]
    end

    subgraph "具体功能"
        READ[读取文件]
        WRITE[写入文件]
        BASH[执行命令]
        SEARCH[代码搜索]
        WEB[网络搜索]
        EDIT[代码编辑]
    end

    TOOLS --> READ
    TOOLS --> WRITE
    TOOLS --> BASH
    TOOLS --> SEARCH
    TOOLS --> WEB
    TOOLS --> EDIT

    AI --> TOOLS
    MCP --> TOOLS
```

### 4.3 为什么 CLI 必须在沙箱中运行

```mermaid
graph TB
    subgraph "安全边界"
        BACKEND[Backend Server]
        E2B[E2B Sandbox]
    end

    subgraph "沙箱内部"
        CLI[Claude CLI]
        FS[用户文件系统]
        PROC[用户进程]
    end

    BACKEND -->|API 调用| E2B
    E2B --> CLI
    CLI --> FS
    CLI --> PROC

    subgraph "隔离保护"
        I1[防止访问生产数据库]
        I2[防止访问其他用户文件]
        I3[防止恶意代码执行]
        I4[资源使用限制]
    end

    E2B -.-> I1
    E2B -.-> I2
    E2B -.-> I3
    E2B -.-> I4

    style E2B fill:#ff9
    style CLI fill:#9cf
```

**安全原因**：
- CLI 可以执行任意代码（用户请求的）
- CLI 可以读写文件系统
- CLI 可以运行 shell 命令
- 必须在隔离环境中运行，防止影响生产系统

## 5. SDK + CLI + Backend 三者关系

### 5.1 职责分工

```mermaid
graph TB
    subgraph "Backend Service"
        direction TB
        B_AUTH[用户认证]
        B_DB[数据持久化]
        B_STREAM[流式分发]
        B_ORCH[服务编排]
    end

    subgraph "Claude Agent SDK"
        direction TB
        S_PROTO[通信协议]
        S_TYPE[类型系统]
        S_PARSE[消息解析]
    end

    subgraph "Claude CLI"
        direction TB
        C_AI[AI 推理]
        C_TOOL[工具执行]
        C_FILE[文件操作]
    end

    B_ORCH --> S_PROTO
    S_PROTO --> C_AI
    C_AI --> C_TOOL
    C_TOOL --> C_FILE

    style B_ORCH fill:#f96
    style S_PROTO fill:#9f6
    style C_AI fill:#69f
```

### 5.2 完整交互时序

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户浏览器
    participant API as FastAPI
    participant Celery as Celery Worker
    participant SDK as Claude Agent SDK
    participant Transport as E2BSandboxTransport
    participant E2B as E2B API
    participant Sandbox as E2B Sandbox
    participant CLI as Claude CLI

    User->>API: POST /chat (发送消息)
    API->>API: 创建 Message 记录
    API->>Celery: 入队异步任务

    rect rgb(240, 248, 255)
        Note over Celery,Sandbox: 沙箱准备阶段
        Celery->>E2B: 连接沙箱
        E2B->>Sandbox: 激活容器
        Celery->>Sandbox: 初始化环境
    end

    rect rgb(255, 248, 240)
        Note over Celery,CLI: SDK 桥接阶段
        Celery->>SDK: 创建 ClaudeSDKClient
        SDK->>Transport: 建立传输通道
        Transport->>Sandbox: 启动 CLI 进程
        Sandbox->>CLI: 执行 claude 命令
    end

    rect rgb(240, 255, 240)
        Note over SDK,CLI: 消息处理循环
        SDK->>Transport: write(user_message)
        Transport->>CLI: stdin JSON

        loop AI 处理
            CLI->>CLI: 推理 + 工具调用
            CLI-->>Transport: stdout JSON
            Transport-->>SDK: 解析消息
            SDK-->>Celery: 类型化事件
            Celery-->>API: Redis 发布
            API-->>User: SSE 推送
        end
    end

    rect rgb(255, 240, 240)
        Note over Celery,Sandbox: 清理阶段
        Celery->>Sandbox: 创建检查点
        Celery->>API: 更新消息状态
    end
```

### 5.3 三者缺一不可的原因

| 组件 | 如果缺少会怎样 |
|------|----------------|
| **Backend** | 无法多用户、无法持久化、无法 Web 访问 |
| **SDK** | 需要手动实现协议、缺乏类型安全、维护成本高 |
| **CLI** | 无法执行 AI 推理、无法调用工具、无法操作文件 |

## 6. 技术实现细节

### 6.1 Transport 桥接实现

```python
# E2BSandboxTransport 实现 SDK 的 Transport 接口
class E2BSandboxTransport(Transport):
    async def connect(self) -> None:
        # 1. 连接 E2B 沙箱
        self._sandbox = await AsyncSandbox.connect(sandbox_id)

        # 2. 构建 CLI 命令
        command = self._build_command()
        # 例如: claude --output-format stream-json --model claude-opus-4-5 ...

        # 3. 启动 CLI 进程
        self._process = await self._sandbox.commands.run(
            command,
            envs={"ANTHROPIC_API_KEY": api_key, ...},
            on_stdout=self._handle_stdout,
            on_stderr=self._handle_stderr,
        )

    async def write(self, data: str) -> None:
        # 向 CLI stdin 写入 JSON
        await self._sandbox.commands.send_stdin(self._process.pid, data)

    async def read_messages(self) -> AsyncIterator[dict]:
        # 从 stdout 读取并解析 JSON
        while self._connected:
            line = await self._output_queue.get()
            parsed = self._parse_cli_output(line)
            if parsed:
                yield parsed
```

### 6.2 CLI 命令构建

```python
def _build_command(self) -> str:
    cmd = ["claude", "--output-format", "stream-json", "--verbose"]

    # 模型选择
    if self._options.model:
        cmd.extend(["--model", self._options.model])

    # 权限模式
    if self._options.permission_mode:
        cmd.extend(["--permission-mode", self._options.permission_mode])

    # 系统提示
    if self._options.system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    # MCP 服务器配置
    if self._options.mcp_servers:
        mcp_config = json.dumps({"mcpServers": self._options.mcp_servers})
        cmd.extend(["--mcp-config", mcp_config])

    # 会话恢复
    if self._options.resume:
        cmd.extend(["--resume", self._options.resume])

    # 流式输入模式
    cmd.extend(["--input-format", "stream-json"])

    return shlex.join(cmd)
```

### 6.3 消息处理流程

```python
async def process_stream(self):
    async with ClaudeSDKClient(transport, options) as client:
        # SDK 返回类型化的消息
        async for message in client.receive_response():
            for block in message.content:
                # 根据 block 类型处理
                if isinstance(block, TextBlock):
                    event = {"type": "assistant_text", "text": block.text}
                elif isinstance(block, ToolUseBlock):
                    event = {"type": "tool_started", "tool": {...}}
                elif isinstance(block, ThinkingBlock):
                    event = {"type": "assistant_thinking", "thinking": block.thinking}

                # 发布到 Redis
                await redis.xadd(f"chat:{chat_id}", event)

                # 保存到数据库
                events.append(event)

        # 保存最终消息
        message.content = json.dumps(events)
        await session.commit()
```

## 7. 总结

### 7.1 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Backend Service                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • 用户认证与授权                                          │  │
│  │  • 多用户隔离与会话管理                                     │  │
│  │  • 数据持久化 (PostgreSQL)                                 │  │
│  │  • 实时流式分发 (Redis + SSE)                              │  │
│  │  • 异步任务处理 (Celery)                                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               Claude Agent SDK (协议层)                     │  │
│  │  • 类型化 API 接口                                         │  │
│  │  • 消息序列化/反序列化                                      │  │
│  │  • Transport 抽象                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            E2BSandboxTransport (桥接层)                     │  │
│  │  • 沙箱连接管理                                            │  │
│  │  • CLI 进程控制                                            │  │
│  │  • stdin/stdout 桥接                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         E2B Sandbox                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               Claude CLI (执行层)                          │  │
│  │  • AI 推理引擎                                             │  │
│  │  • 工具执行 (文件、命令、搜索)                              │  │
│  │  • MCP 服务器                                              │  │
│  │  • 会话状态管理                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 关键结论

1. **Backend Service** = 多用户 Web 应用层（持久化、认证、流式传输）
2. **Claude Agent SDK** = 协议抽象层（类型安全、版本兼容）
3. **Claude CLI** = AI 执行层（推理、工具、文件操作）
4. **E2B Sandbox** = 安全隔离层（保护生产环境）

四者协同工作，将单用户命令行工具转变为安全、可扩展的多用户 Web 服务。
