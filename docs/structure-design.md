# 系统架构设计深度解析

## 1. 整体架构概览

### 1.1 系统架构图

```mermaid
graph TB
    subgraph "Frontend Layer"
        REACT[React SPA<br/>Port 3000]
        ZUSTAND[Zustand Store]
        RQ[React Query]
    end

    subgraph "Backend Layer"
        FASTAPI[FastAPI Server<br/>Port 8080]
        CELERY[Celery Workers]
    end

    subgraph "Data Layer"
        PG[(PostgreSQL 13)]
        REDIS[(Redis 7)]
    end

    subgraph "External Services"
        CLAUDE[Claude API]
        E2B[E2B Sandbox]
    end

    REACT --> |HTTP/SSE| FASTAPI
    REACT --> |WebSocket| FASTAPI
    ZUSTAND --> REACT
    RQ --> REACT

    FASTAPI --> PG
    FASTAPI --> REDIS
    CELERY --> REDIS
    CELERY --> PG

    CELERY --> CLAUDE
    CELERY --> E2B
```

### 1.2 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **Frontend** | React + TypeScript + Vite | 用户界面 |
| **状态管理** | Zustand + React Query | 客户端状态 + 服务端缓存 |
| **Backend** | FastAPI + Python 3.11+ | REST API 服务 |
| **异步任务** | Celery | 后台任务处理 |
| **数据库** | PostgreSQL 13 | 持久化存储 |
| **缓存/消息** | Redis 7 | 缓存 + Pub/Sub + Stream |
| **AI 引擎** | Claude API + Claude Agent SDK | AI 能力 |
| **沙箱** | E2B | 隔离代码执行 |

## 2. Backend 服务架构

### 2.1 分层架构

```mermaid
graph TB
    subgraph "API Layer"
        ENDPOINTS[API Endpoints<br/>/api/v1/*]
    end

    subgraph "Service Layer"
        CS[ChatService]
        CAS[ClaudeAgentService]
        SS[SandboxService]
        MS[MessageService]
        US[UserService]
    end

    subgraph "Data Access Layer"
        MODELS[SQLAlchemy Models]
        SCHEMAS[Pydantic Schemas]
    end

    subgraph "Infrastructure"
        DB[Database Session]
        CACHE[Redis Client]
        CELERY_APP[Celery App]
    end

    ENDPOINTS --> CS
    ENDPOINTS --> SS
    CS --> CAS
    CS --> MS
    CAS --> SS
    SS --> MODELS
    MS --> MODELS
    MODELS --> DB
    CS --> CELERY_APP
    CELERY_APP --> CACHE
```

### 2.2 依赖注入

```python
# core/deps.py - 依赖注入链

@asynccontextmanager
async def get_chat_service(
    file_service: FileService,
    sandbox_service: SandboxService,
    user_service: UserService,
) -> AsyncIterator[ChatService]:
    """
    构建完整的服务依赖链
    """
    claude_agent_service = ClaudeAgentService(sandbox_service)
    chat_service = ChatService(
        file_service=file_service,
        sandbox_service=sandbox_service,
        user_service=user_service,
        claude_agent_service=claude_agent_service,
    )
    yield chat_service
```

### 2.3 数据库会话管理

```mermaid
graph LR
    subgraph "API Context"
        API_REQ[API Request]
        API_SESSION[SessionLocal<br/>连接池模式]
    end

    subgraph "Celery Context"
        CELERY_TASK[Celery Task]
        CELERY_SESSION[CelerySessionLocal<br/>无池模式]
    end

    subgraph "PostgreSQL"
        PG[(Database)]
    end

    API_REQ --> API_SESSION
    API_SESSION --> |pool_size=30| PG

    CELERY_TASK --> CELERY_SESSION
    CELERY_SESSION --> |NullPool| PG
```

**为什么需要两种会话?**

Celery Worker 使用 fork 创建进程，会继承父进程的数据库连接池，导致 "connection already closed" 错误。因此 Celery 使用 `NullPool` 每次创建新连接。

## 3. Backend 与 E2B 关系深度解析

### 3.1 E2B 是什么?

E2B (Environment-to-Backend) 是一个云端沙箱服务，提供：
- **隔离环境**: 每个用户会话独立的 Linux 容器
- **安全执行**: 代码在隔离环境中运行，不影响主机
- **持久化**: 沙箱可以暂停和恢复
- **文件系统**: 完整的 Linux 文件系统访问

### 3.2 交互架构

```mermaid
graph TB
    subgraph "Backend Server"
        API[FastAPI]
        CELERY[Celery Worker]
        CAS[ClaudeAgentService]
        SS[SandboxService]
        ET[E2BSandboxTransport]
    end

    subgraph "E2B Cloud"
        E2B_API[E2B API]
        SANDBOX[Sandbox Container]
    end

    subgraph "Sandbox 内部"
        CLI[Claude CLI]
        PS[Permission Server]
        VSC[OpenVSCode Server]
        PTY[PTY Session]
        FS[/home/user/]
    end

    API --> CELERY
    CELERY --> CAS
    CAS --> SS
    CAS --> ET

    SS --> |REST API| E2B_API
    ET --> |WebSocket| E2B_API

    E2B_API --> SANDBOX
    SANDBOX --> CLI
    SANDBOX --> PS
    SANDBOX --> VSC
    SANDBOX --> PTY
    SANDBOX --> FS
```

### 3.3 完整请求生命周期

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as Frontend
    participant API as FastAPI
    participant CEL as Celery Worker
    participant SS as SandboxService
    participant ET as E2BSandboxTransport
    participant E2B as E2B API
    participant SB as Sandbox
    participant CLI as Claude CLI

    U->>FE: 发送消息
    FE->>API: POST /chat
    API->>API: 创建 Message 记录
    API->>CEL: 发布 Celery Task

    Note over API,FE: SSE 连接保持

    CEL->>SS: 初始化沙箱
    SS->>E2B: 连接沙箱
    E2B->>SB: 激活容器

    CEL->>SS: initialize_sandbox()
    SS->>SB: 启动 OpenVSCode (port 8765)
    SS->>SB: 设置环境变量
    SS->>SB: 配置 GitHub Token
    SS->>SB: 复制自定义 Skills/Commands

    CEL->>ET: 建立传输通道
    ET->>E2B: WebSocket 连接
    ET->>SB: 启动 Claude CLI

    loop 消息处理
        CLI->>CLI: 处理请求
        CLI-->>ET: stream-json 输出
        ET-->>CEL: 解析事件
        CEL-->>API: Redis Pub/Sub
        API-->>FE: SSE 事件
        FE-->>U: 渲染响应
    end

    CLI->>SB: 执行工具/代码
    SB-->>CLI: 返回结果

    CEL->>SS: 创建检查点
    SS->>SB: rsync 增量备份
    CEL->>API: 更新消息状态
```

### 3.4 SandboxService 核心功能

```mermaid
classDiagram
    class SandboxService {
        +api_key: str
        +create_sandbox() AsyncSandbox
        +delete_sandbox(sandbox_id)
        +get_or_connect_sandbox(sandbox_id) AsyncSandbox
        +execute_command(sandbox_id, command, background) Result
        +write_file(sandbox_id, path, content)
        +get_file_content(sandbox_id, path) bytes
        +create_pty_session(sandbox_id) PtySession
        +send_pty_input(sandbox_id, data)
        +initialize_sandbox(sandbox, settings, chat_id)
        +create_checkpoint(sandbox_id, message_id)
        +restore_checkpoint(sandbox_id, checkpoint_id)
        +get_secrets(sandbox_id) dict
    }

    class AsyncSandbox {
        +id: str
        +files: FilesModule
        +commands: CommandsModule
        +process: ProcessModule
    }

    SandboxService --> AsyncSandbox : manages
```

### 3.5 E2BSandboxTransport 详解

```mermaid
classDiagram
    class E2BSandboxTransport {
        -sandbox: AsyncSandbox
        -process: Process
        -output_queue: asyncio.Queue
        +connect() void
        +disconnect() void
        +write(data: bytes) void
        +read_messages() AsyncIterator
        -_build_command() str
        -_parse_cli_output(line) dict
        -_monitor_process() void
    }

    class Transport {
        <<interface>>
        +connect()
        +disconnect()
        +write(data)
        +read_messages()
    }

    E2BSandboxTransport ..|> Transport : implements
```

**核心职责**:
1. **connect()**: 连接 E2B 沙箱，启动 Claude CLI 进程
2. **write()**: 向 Claude CLI stdin 写入 JSON 消息
3. **read_messages()**: 从 stdout 读取并解析 stream-json 输出
4. **_parse_cli_output()**: 去除 ANSI 转义码，解析 JSON

### 3.6 Claude CLI 调用构建

```python
# e2b_transport.py::_build_command()

def _build_command(self) -> str:
    """
    构建 Claude CLI 命令行
    """
    cmd_parts = [
        "claude",
        "--output-format", "stream-json",
        "--verbose",
        "--append-system-prompt", quote(system_prompt),
        "--permission-mode", permission_mode,
        "--model", model_id,
        "--mcp-config", quote(json.dumps(mcp_config)),
        "--input-format", "stream-json",
    ]

    if resume_session_id:
        cmd_parts.extend(["--resume", resume_session_id])

    return " ".join(cmd_parts)
```

**生成示例**:
```bash
claude --output-format stream-json --verbose \
  --append-system-prompt "You are working in sandbox..." \
  --permission-mode auto \
  --model claude-opus-4-5 \
  --mcp-config '{"mcpServers": {"permission": {...}}}' \
  --input-format stream-json \
  --resume abc123
```

## 4. 数据流架构

### 4.1 消息处理流程

```mermaid
flowchart TB
    subgraph "Input"
        USER[用户输入]
        FILES[附件文件]
    end

    subgraph "Processing"
        PREP[prepare_user_prompt]
        STREAM[get_ai_stream]
        PROC[StreamProcessor]
    end

    subgraph "Storage"
        MSG[(Message)]
        ATTACH[(Attachment)]
        REDIS[(Redis Stream)]
    end

    subgraph "Output"
        SSE[SSE Response]
        WS[WebSocket]
    end

    USER --> PREP
    FILES --> PREP
    PREP --> STREAM
    STREAM --> PROC

    PROC --> MSG
    FILES --> ATTACH
    PROC --> REDIS

    REDIS --> SSE
    REDIS --> WS
```

### 4.2 事件存储格式

```json
// Message.content 存储格式
[
    {"type": "user_text", "text": "帮我写一个排序算法"},
    {"type": "assistant_thinking", "thinking": "用户需要..."},
    {"type": "assistant_text", "text": "我来帮你实现一个快速排序..."},
    {"type": "tool_started", "tool": {"id": "xyz", "name": "Write", "input": {...}}},
    {"type": "tool_completed", "tool": {"id": "xyz", "result": "File created"}},
    {"type": "assistant_text", "text": "代码已经创建完成..."}
]
```

## 5. 实时通信架构

### 5.1 SSE (Server-Sent Events)

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI
    participant REDIS as Redis
    participant WORKER as Celery Worker

    FE->>API: GET /chat/{id}/stream<br/>Accept: text/event-stream

    loop 直到完成
        WORKER->>REDIS: XADD stream event
        API->>REDIS: XREAD BLOCK
        REDIS-->>API: 返回事件
        API-->>FE: SSE: data: {...}
    end

    Note over FE,API: 支持 Last-Event-ID 断线重连
```

### 5.2 WebSocket (终端)

```mermaid
sequenceDiagram
    participant FE as Frontend (xterm.js)
    participant API as FastAPI
    participant SS as SandboxService
    participant SB as E2B Sandbox

    FE->>API: WS /ws/chat/{id}/pty
    API->>SS: create_pty_session()
    SS->>SB: 创建 PTY

    loop 终端交互
        FE->>API: 用户输入
        API->>SB: send_pty_input()
        SB-->>API: 终端输出
        API-->>FE: 显示输出
    end
```

## 6. 安全架构

### 6.1 隔离层次

```mermaid
graph TB
    subgraph "用户层"
        U1[用户 A]
        U2[用户 B]
    end

    subgraph "Backend 层"
        AUTH[认证中间件]
        PERM[权限检查]
    end

    subgraph "沙箱层"
        SB1[Sandbox A<br/>隔离容器]
        SB2[Sandbox B<br/>隔离容器]
    end

    U1 --> AUTH
    U2 --> AUTH
    AUTH --> PERM

    PERM --> |用户 A 的请求| SB1
    PERM --> |用户 B 的请求| SB2

    SB1 -.->|完全隔离| SB2
```

### 6.2 权限控制流程

```mermaid
flowchart TD
    A[工具调用请求] --> B{权限模式?}

    B -->|plan| C[自动批准]
    B -->|bypassPermissions| C
    B -->|ask| D[请求用户批准]
    B -->|auto| E{工具类型?}

    E -->|安全工具| C
    E -->|危险工具| D

    D --> F{用户决定}
    F -->|批准| G[执行工具]
    F -->|拒绝| H[跳过工具]

    C --> G
```

### 6.3 敏感信息保护

```python
# 环境变量安全传递
envs = {
    "ANTHROPIC_API_KEY": api_key,      # 仅在沙箱内有效
    "GITHUB_TOKEN": github_token,       # 自动配置 git
    **user_custom_env_vars,             # 用户自定义变量
}

# 这些变量在沙箱外部不可访问
```

## 7. 扩展性设计

### 7.1 水平扩展

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Nginx / Traefik]
    end

    subgraph "API Instances"
        API1[FastAPI 1]
        API2[FastAPI 2]
        API3[FastAPI N]
    end

    subgraph "Worker Pool"
        W1[Celery Worker 1]
        W2[Celery Worker 2]
        W3[Celery Worker N]
    end

    subgraph "Shared State"
        REDIS[(Redis Cluster)]
        PG[(PostgreSQL)]
    end

    LB --> API1
    LB --> API2
    LB --> API3

    API1 --> REDIS
    API2 --> REDIS
    API3 --> REDIS

    W1 --> REDIS
    W2 --> REDIS
    W3 --> REDIS

    API1 --> PG
    W1 --> PG
```

### 7.2 模块化设计

```mermaid
graph LR
    subgraph "Core Modules"
        CHAT[Chat Module]
        SANDBOX[Sandbox Module]
        AGENT[Agent Module]
    end

    subgraph "Extension Modules"
        SKILLS[Skills Module]
        COMMANDS[Commands Module]
        CUSTOM_AGENTS[Custom Agents Module]
        MCP[MCP Module]
    end

    subgraph "Integration Modules"
        AUTH[Auth Module]
        STORAGE[Storage Module]
        SCHEDULER[Scheduler Module]
    end

    CHAT --> AGENT
    AGENT --> SANDBOX
    AGENT --> MCP

    SKILLS --> AGENT
    COMMANDS --> CHAT
    CUSTOM_AGENTS --> AGENT
```

## 8. 性能优化策略

### 8.1 连接池配置

```python
# 数据库连接池
engine = create_async_engine(
    DATABASE_URL,
    pool_size=30,           # 基础连接数
    max_overflow=20,        # 最大溢出连接
    pool_recycle=3600,      # 连接回收时间
    pool_pre_ping=True,     # 连接健康检查
)
```

### 8.2 缓存策略

```mermaid
graph LR
    REQ[API 请求] --> CACHE{Redis 缓存}

    CACHE -->|命中| RESP[快速响应]
    CACHE -->|未命中| DB[(数据库)]
    DB --> UPDATE[更新缓存]
    UPDATE --> RESP
```

### 8.3 沙箱资源优化

- **auto_pause**: 沙箱空闲时自动暂停，节省资源
- **检查点复用**: 使用硬链接减少存储占用
- **增量同步**: rsync 只传输变化的文件

## 9. 监控与可观测性

### 9.1 日志架构

```mermaid
graph TB
    subgraph "应用层"
        API_LOG[API 日志]
        CELERY_LOG[Celery 日志]
        SANDBOX_LOG[沙箱日志]
    end

    subgraph "聚合层"
        COLLECTOR[日志收集器]
    end

    subgraph "存储层"
        ES[Elasticsearch]
        METRICS[Prometheus]
    end

    API_LOG --> COLLECTOR
    CELERY_LOG --> COLLECTOR
    SANDBOX_LOG --> COLLECTOR

    COLLECTOR --> ES
    COLLECTOR --> METRICS
```

### 9.2 健康检查

```python
# 健康检查端点
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": await check_db_connection(),
        "redis": await check_redis_connection(),
        "e2b": await check_e2b_api(),
    }
```

## 10. 部署架构

### 10.1 容器化部署

```mermaid
graph TB
    subgraph "Docker Compose"
        FE[frontend<br/>:3000]
        BE[backend<br/>:8080]
        WORKER[celery-worker]
        PG[postgres<br/>:5432]
        REDIS[redis<br/>:6379]
    end

    subgraph "External"
        E2B[E2B Cloud]
        CLAUDE[Claude API]
    end

    FE --> BE
    BE --> PG
    BE --> REDIS
    WORKER --> PG
    WORKER --> REDIS
    WORKER --> E2B
    WORKER --> CLAUDE
```

### 10.2 环境配置

```bash
# 核心环境变量
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key
ANTHROPIC_API_KEY=sk-ant-...
E2B_API_KEY=e2b_...
E2B_TEMPLATE_ID=custom-template-id
ENVIRONMENT=development|production
```
