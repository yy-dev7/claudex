# Claude Agent 架构深度解析

## 1. 概述

Claude Agent 是本系统的核心 AI 引擎，负责处理用户请求、调用工具、执行代码并生成响应。它基于 Claude Agent SDK 构建，通过 E2B 沙箱环境实现安全的代码执行。

## 2. 核心组件

### 2.1 组件关系图

```mermaid
graph TB
    subgraph "Backend Services"
        CAS[ClaudeAgentService]
        CS[ChatService]
        SS[SandboxService]
        ET[E2BSandboxTransport]
        TH[ToolHandlerRegistry]
        SP[StreamProcessor]
    end

    subgraph "External Services"
        SDK[Claude Agent SDK]
        E2B[E2B Sandbox API]
        REDIS[Redis Pub/Sub]
        PG[(PostgreSQL)]
    end

    subgraph "E2B Sandbox Environment"
        CLI[Claude CLI]
        PS[Permission Server]
        MCP[MCP Servers]
        FS[File System]
    end

    CS --> CAS
    CAS --> SS
    CAS --> ET
    CAS --> TH
    CAS --> SP

    ET --> SDK
    ET --> E2B
    SS --> E2B

    SDK --> CLI
    CLI --> PS
    CLI --> MCP
    CLI --> FS

    SP --> REDIS
    CS --> PG
```

### 2.2 核心服务职责

| 服务 | 文件位置 | 核心职责 |
|------|----------|----------|
| **ClaudeAgentService** | `services/claude_agent.py` | 编排 Claude SDK 与 E2B 沙箱的交互 |
| **SandboxService** | `services/sandbox.py` | 管理 E2B 沙箱生命周期和操作 |
| **E2BSandboxTransport** | `services/e2b_transport.py` | 实现 Transport 接口，桥接 Claude SDK 与 E2B |
| **ChatService** | `services/chat.py` | 高层聊天操作，消息管理 |
| **ToolHandlerRegistry** | `services/tool_handler.py` | 追踪和管理工具执行状态 |
| **StreamProcessor** | `services/streaming/processor.py` | 处理流式事件，发布到 Redis |

## 3. Claude Agent SDK 集成

### 3.1 SDK 配置构建流程

```mermaid
flowchart TD
    A[用户发送消息] --> B[ChatService.send_message]
    B --> C[Celery Task: process_chat]
    C --> D[ClaudeAgentService.get_ai_stream]

    D --> E{构建配置}
    E --> F[_build_claude_options]
    E --> G[_get_mcp_servers]
    E --> H[_build_permission_server]

    F --> I[ClaudeAgentOptions]
    G --> I
    H --> I

    I --> J[ClaudeSDKClient]
    J --> K[E2BSandboxTransport]
    K --> L[Claude CLI in E2B]
```

### 3.2 ClaudeAgentOptions 配置详解

```python
ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",      # 使用 Claude Code 预设
        "append": custom_system_prompt # 追加自定义系统提示
    },
    permission_mode="auto",            # plan/ask/auto/bypassPermissions
    model="claude-opus-4-5",           # AI 模型选择
    mcp_servers={...},                 # MCP 服务器配置
    cwd="/home/user",                  # 工作目录
    user="user",                       # 沙箱用户
    resume=session_id,                 # 会话恢复 ID
    env={...},                         # 环境变量
    max_thinking_tokens=thinking_mode, # 扩展思考预算
)
```

### 3.3 Transport 接口与 E2BSandboxTransport

#### 3.3.1 Transport 抽象接口

`Transport` 是 Claude Agent SDK 提供的**抽象基类**，定义了与 Claude CLI 通信的标准协议：

```python
# Claude Agent SDK 定义的接口
from claude_agent_sdk._internal.transport import Transport

class Transport(ABC):
    async def connect(self) -> None: ...      # 建立连接
    async def close(self) -> None: ...        # 关闭连接
    async def write(self, data: str) -> None: ... # 写入数据到 CLI stdin
    def read_messages(self) -> AsyncIterator[dict]: ... # 读取 CLI stdout
    async def end_input(self) -> None: ...    # 发送 EOF 信号
    def is_ready(self) -> bool: ...           # 检查连接状态
```

#### 3.3.2 E2BSandboxTransport 实现

`E2BSandboxTransport` 是**本项目自定义实现**的 Transport，用于适配 E2B 云沙箱环境：

```python
# services/e2b_transport.py
from claude_agent_sdk._internal.transport import Transport

class E2BSandboxTransport(Transport):
    """将 Transport 接口适配到 E2B 沙箱环境"""

    async def connect(self) -> None:
        # 1. 连接 E2B 沙箱
        self._sandbox = await AsyncSandbox.connect(sandbox_id, api_key)

        # 2. 构建 Claude CLI 命令
        command = self._build_command()

        # 3. 在沙箱中启动 CLI 进程
        self._command = await self._sandbox.commands.run(command, ...)

    async def write(self, data: str) -> None:
        # 向 CLI stdin 写入 JSON
        await self._sandbox.commands.send_stdin(self._command.pid, data)

    def read_messages(self) -> AsyncIterator[dict]:
        # 从 stdout 读取并解析 JSON（去除 ANSI 转义码）
        return self._parse_cli_output()
```

#### 3.3.3 架构设计意图

```mermaid
graph TB
    subgraph "Claude Agent SDK 提供"
        TRANSPORT[Transport<br/>抽象接口]
    end

    subgraph "本项目实现"
        E2B_IMPL[E2BSandboxTransport<br/>E2B 云沙箱]
    end

    subgraph "可扩展的其他实现"
        LOCAL[LocalTransport<br/>本地进程]
        DOCKER[DockerTransport<br/>Docker 容器]
        SSH[SSHTransport<br/>远程服务器]
        FLY[FlyTransport<br/>Fly.io]
    end

    TRANSPORT -.->|继承实现| E2B_IMPL
    TRANSPORT -.->|可扩展| LOCAL
    TRANSPORT -.->|可扩展| DOCKER
    TRANSPORT -.->|可扩展| SSH
    TRANSPORT -.->|可扩展| FLY

    style E2B_IMPL fill:#9f9
```

**设计优势**：

| 层级 | 提供者 | 职责 |
|------|--------|------|
| **Transport 接口** | Claude Agent SDK | 定义通信协议规范 |
| **E2BSandboxTransport** | 本项目 | 适配 E2B 沙箱环境 |

- SDK 只定义"怎么通信"，不关心"在哪里运行 CLI"
- 项目可以自由选择运行环境（E2B、Docker、本地等）
- 切换沙箱提供商只需实现新的 Transport 类

### 3.4 权限模式详解

```mermaid
graph LR
    subgraph "Permission Modes"
        PLAN[plan<br/>自动批准所有]
        ASK[ask<br/>每次都询问用户]
        AUTO[auto<br/>智能判断]
        BYPASS[bypassPermissions<br/>跳过检查]
    end

    AUTO --> |安全操作| APPROVE[自动批准]
    AUTO --> |危险操作| REQUEST[请求用户批准]

    ASK --> REQUEST
    PLAN --> APPROVE
    BYPASS --> APPROVE
```

## 4. MCP 服务器架构

### 4.1 MCP 服务器类型

```mermaid
graph TB
    subgraph "MCP Server Types"
        NPX[npx<br/>Node.js 包]
        UVX[uvx<br/>Python 包]
        HTTP[http<br/>HTTP 服务]
        SDK_TYPE[sdk<br/>Python SDK 类型]
    end

    subgraph "Built-in Servers"
        PERM[Permission Server<br/>权限审批]
        ZAI[Z.AI MCP<br/>Z.AI 集成]
        WEB[Web Search Prime<br/>网络搜索]
    end

    subgraph "Custom Servers"
        USER_MCP[用户自定义 MCP]
    end

    NPX --> USER_MCP
    UVX --> USER_MCP
    HTTP --> USER_MCP
    SDK_TYPE --> USER_MCP
```

### 4.2 Permission Server 工作流程

```mermaid
sequenceDiagram
    participant CLI as Claude CLI
    participant PS as Permission Server
    participant API as Backend API
    participant USER as 用户

    CLI->>PS: 调用危险工具
    PS->>API: POST /permissions/request
    API->>USER: SSE 推送权限请求
    USER->>API: 批准/拒绝
    API->>PS: 返回决定
    PS->>CLI: 返回权限结果

    alt 批准
        CLI->>CLI: 执行工具
    else 拒绝
        CLI->>CLI: 跳过工具
    end
```

## 5. 工具处理机制

### 5.1 ToolHandlerRegistry 状态机

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Started: start_tool()
    Started --> Completed: finish_tool(success)
    Started --> Failed: finish_tool(error)
    Started --> Started: 嵌套工具调用
    Completed --> [*]
    Failed --> [*]
```

### 5.2 工具结果规范化

```python
class ToolHandlerRegistry:
    def _normalize_result(self, result) -> JSONValue:
        """
        递归解析 JSON 编码的字符串结果
        处理嵌套的数组/字典
        """
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                return self._normalize_result(parsed)
            except json.JSONDecodeError:
                return result
        # ... 递归处理嵌套结构
```

## 6. 流式处理架构

### 6.1 事件类型

```typescript
type StreamEventType =
    | "assistant_text"      // AI 文本输出
    | "assistant_thinking"  // 扩展思考内容
    | "tool_started"        // 工具开始执行
    | "tool_completed"      // 工具执行完成
    | "tool_failed"         // 工具执行失败
    | "user_text"           // 用户输入
    | "system"              // 系统消息
    | "permission_request"  // 权限请求
```

### 6.2 事件流处理管道

```mermaid
flowchart LR
    subgraph "Claude CLI"
        OUT[stdout stream-json]
    end

    subgraph "E2BSandboxTransport"
        PARSE[_parse_cli_output<br/>解析 JSON + 去除 ANSI]
        QUEUE[async queue]
    end

    subgraph "StreamProcessor"
        PROC[process_event]
        EMIT[emit_event]
    end

    subgraph "Distribution"
        REDIS[(Redis Stream)]
        SSE[SSE Endpoint]
        DB[(PostgreSQL)]
    end

    OUT --> PARSE
    PARSE --> QUEUE
    QUEUE --> PROC
    PROC --> EMIT
    EMIT --> REDIS
    REDIS --> SSE
    EMIT --> DB
```

## 7. 会话管理

### 7.1 会话恢复机制

```mermaid
sequenceDiagram
    participant USER as 用户
    participant API as Backend API
    participant AGENT as ClaudeAgentService
    participant E2B as E2B Sandbox

    Note over USER,E2B: 新会话
    USER->>API: 发送消息 (chat_id)
    API->>AGENT: get_ai_stream(session_id=None)
    AGENT->>E2B: 创建新会话
    E2B-->>AGENT: 返回 session_id
    API->>API: 保存 session_id 到 Chat

    Note over USER,E2B: 恢复会话
    USER->>API: 发送消息 (同一 chat_id)
    API->>AGENT: get_ai_stream(session_id=saved_id)
    AGENT->>E2B: claude --resume {session_id}
    E2B-->>AGENT: 恢复上下文
```

### 7.2 检查点系统

检查点使用 rsync 的 `--link-dest` 实现增量备份：

```bash
rsync -a --delete \
  --link-dest=previous_checkpoint \
  --exclude=.checkpoints \
  --exclude=.cache \
  /home/user/ \
  /home/user/.checkpoints/{message_id}/
```

**优势**:
- 只有修改的文件占用磁盘空间
- 未修改文件通过硬链接共享
- 支持快速恢复到任意消息点
- 每个沙箱最多 20 个检查点

## 8. 错误处理与重试

### 8.1 错误处理策略

```mermaid
flowchart TD
    A[Claude CLI 输出] --> B{解析结果}

    B -->|成功| C[正常处理]
    B -->|JSON 解析错误| D[记录日志并继续]
    B -->|连接错误| E{重试策略}

    E -->|重试次数 < 3| F[等待后重试]
    E -->|重试次数 >= 3| G[标记消息失败]

    F --> A
    G --> H[通知用户]

    C --> I[发布事件]
    D --> I
```

### 8.2 取消机制

```mermaid
sequenceDiagram
    participant USER as 用户
    participant API as Backend API
    participant REDIS as Redis
    participant WORKER as Celery Worker
    participant E2B as E2B Sandbox

    USER->>API: 取消请求
    API->>REDIS: 发布取消信号

    loop 每 100ms
        WORKER->>REDIS: 检查取消信号
    end

    WORKER->>WORKER: 检测到取消
    WORKER->>E2B: 终止进程
    WORKER->>API: 更新消息状态为 interrupted
```

## 9. 性能优化

### 9.1 并行处理

- **流式输出**: 边生成边输出，无需等待完整响应
- **Redis Stream**: 支持 SSE 断线重连，通过 Last-Event-ID 恢复
- **双任务监控**: 主任务处理流，监控任务检查取消

### 9.2 资源管理

```python
# 异步上下文管理器确保资源清理
async with ClaudeAgentService(...) as ai_service:
    async with E2BSandboxTransport(...) as transport:
        async with ClaudeSDKClient(...) as client:
            # 所有清理自动执行
```

## 10. 扩展机制

### 10.1 自定义 Skills

用户可以创建自定义 Skills，在聊天中通过 `/skill` 命令调用：

```mermaid
graph LR
    A["用户消息<br/>/skill:name"] --> B[识别 Skill 调用]
    B --> C[加载 Skill 定义]
    C --> D[注入到系统提示]
    D --> E[Claude 执行 Skill]
```

### 10.2 自定义 Commands

Slash Commands 提供快捷操作：

```mermaid
graph LR
    A["/command args"] --> B[CommandService]
    B --> C[解析命令定义]
    C --> D[替换变量]
    D --> E[执行命令逻辑]
```

### 10.3 自定义 Agents

用户可以定义专门的 Agent 角色：

```mermaid
graph LR
    A["@agent 任务"] --> B[AgentService]
    B --> C[加载 Agent 配置]
    C --> D[构建专用提示]
    D --> E[启动 Agent 会话]
```
