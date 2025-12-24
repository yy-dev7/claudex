# 架构设计深度分析报告

## 目录

1. [核心架构关系](#1-核心架构关系)
2. [Backend 与 E2B 交互深度解析](#2-backend-与-e2b-交互深度解析)
3. [架构设计问题分析](#3-架构设计问题分析)
4. [优化建议](#4-优化建议)

---

## 1. 核心架构关系

### 1.1 系统全景图

```mermaid
graph TB
    subgraph "用户层"
        USER[用户浏览器]
    end

    subgraph "前端层 - Port 3000"
        REACT[React SPA]
        STORE[Zustand Store]
        QUERY[React Query]
    end

    subgraph "后端层 - Port 8080"
        direction TB
        FASTAPI[FastAPI Server]
        CELERY[Celery Workers]
    end

    subgraph "数据层"
        PG[(PostgreSQL)]
        REDIS[(Redis)]
    end

    subgraph "AI 引擎层"
        SDK[Claude Agent SDK]
        TRANSPORT[E2BSandboxTransport]
    end

    subgraph "沙箱层 - E2B Cloud"
        E2B_API[E2B API]
        SANDBOX[Sandbox Container]
        CLI[Claude CLI]
        PS[Permission Server]
        VSC[OpenVSCode]
    end

    USER --> REACT
    REACT --> STORE
    REACT --> QUERY
    QUERY -->|HTTP/SSE| FASTAPI
    REACT -->|WebSocket| FASTAPI

    FASTAPI --> PG
    FASTAPI --> REDIS
    FASTAPI --> CELERY
    CELERY --> REDIS
    CELERY --> PG

    CELERY --> SDK
    SDK --> TRANSPORT
    TRANSPORT --> E2B_API

    E2B_API --> SANDBOX
    SANDBOX --> CLI
    SANDBOX --> PS
    SANDBOX --> VSC

    style E2B_API fill:#f96,stroke:#333
    style SANDBOX fill:#9f6,stroke:#333
    style CLI fill:#69f,stroke:#333
```

### 1.2 关键组件职责矩阵

| 组件 | 职责 | 依赖 | 被依赖 |
|------|------|------|--------|
| **FastAPI** | HTTP 请求处理、认证、路由 | PostgreSQL, Redis | 用户请求 |
| **Celery** | 异步任务执行、长时运算 | Redis, PostgreSQL | FastAPI |
| **ClaudeAgentService** | AI 交互编排、流处理 | SandboxService, SDK | Celery Task |
| **SandboxService** | 沙箱生命周期管理 | E2B API | ClaudeAgentService |
| **E2BSandboxTransport** | SDK ↔ E2B 桥接 | E2B Sandbox | Claude SDK |
| **Claude CLI** | AI 推理、工具调用 | MCP Servers | Transport |
| **Permission Server** | 权限审批代理 | Backend API | Claude CLI |

---

## 2. Backend 与 E2B 交互深度解析

### 2.1 交互时序图

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户
    participant FE as Frontend
    participant API as FastAPI
    participant Celery as Celery Worker
    participant SS as SandboxService
    participant ET as E2BSandboxTransport
    participant E2B as E2B API
    participant Sandbox as E2B Sandbox
    participant CLI as Claude CLI
    participant PS as Permission Server

    User->>FE: 发送消息
    FE->>API: POST /api/v1/chat
    API->>API: 创建 Message 记录
    API->>Celery: 发布异步任务
    API-->>FE: 返回 Task ID

    Note over FE,API: 建立 SSE 连接等待结果

    rect rgb(240, 248, 255)
        Note over Celery,Sandbox: 沙箱初始化阶段
        Celery->>SS: get_or_connect_sandbox()
        SS->>E2B: AsyncSandbox.connect()
        E2B->>Sandbox: 激活容器
        Sandbox-->>SS: 连接成功

        Celery->>SS: initialize_sandbox()
        SS->>Sandbox: 启动 OpenVSCode (:8765)
        SS->>Sandbox: 设置环境变量
        SS->>Sandbox: 配置 GitHub Token
        SS->>Sandbox: 复制 Skills/Commands/Agents
        SS->>Sandbox: 启动 Anthropic Bridge
    end

    rect rgb(255, 248, 240)
        Note over Celery,CLI: Claude CLI 启动阶段
        Celery->>ET: __aenter__()
        ET->>Sandbox: 构建 Claude CLI 命令
        ET->>Sandbox: 执行 Claude CLI 进程
        Sandbox->>CLI: 进程启动

        CLI->>CLI: 加载 MCP 配置
        CLI->>PS: 连接 Permission Server
    end

    rect rgb(240, 255, 240)
        Note over Celery,PS: 消息处理循环
        Celery->>ET: write(user_message)
        ET->>CLI: stdin JSON 输入

        loop AI 处理循环
            CLI->>CLI: 推理生成响应
            CLI-->>ET: stdout stream-json

            opt 需要执行工具
                CLI->>Sandbox: 执行文件/命令操作
                Sandbox-->>CLI: 返回结果

                opt 危险操作需要审批
                    CLI->>PS: 请求权限
                    PS->>API: HTTP POST /permissions/request
                    API-->>FE: SSE 推送权限请求
                    FE-->>User: 显示权限对话框
                    User->>FE: 批准/拒绝
                    FE->>API: 提交决定
                    API-->>PS: 返回决定
                    PS-->>CLI: 权限结果
                end
            end

            ET-->>Celery: 解析后的事件
            Celery-->>API: Redis 发布事件
            API-->>FE: SSE 事件流
            FE-->>User: 渲染响应
        end
    end

    rect rgb(255, 240, 240)
        Note over Celery,Sandbox: 清理阶段
        Celery->>SS: create_checkpoint()
        SS->>Sandbox: rsync 增量备份
        Celery->>ET: __aexit__()
        ET->>CLI: 终止进程
        Celery->>API: 更新 Message 状态
    end
```

### 2.2 E2B 沙箱内部架构

```mermaid
graph TB
    subgraph "E2B Sandbox Container"
        subgraph "进程管理"
            CLAUDE_CLI[Claude CLI Process]
            VSCODE[OpenVSCode Server :8765]
            BRIDGE[Anthropic Bridge :8095]
        end

        subgraph "MCP 服务器"
            PS[Permission Server]
            CUSTOM_MCP[用户自定义 MCP]
        end

        subgraph "文件系统"
            HOME[/home/user/]
            CHECKPOINTS[/.checkpoints/]
            SKILLS[/.skills/]
            COMMANDS[/.commands/]
        end

        subgraph "环境配置"
            ENV[环境变量]
            GIT[Git 配置]
        end
    end

    CLAUDE_CLI --> PS
    CLAUDE_CLI --> CUSTOM_MCP
    CLAUDE_CLI --> HOME
    CLAUDE_CLI --> ENV

    VSCODE --> HOME
    BRIDGE --> ENV

    PS -.->|HTTP| BACKEND[Backend API]
```

### 2.3 数据流详解

```mermaid
flowchart LR
    subgraph "输入流"
        USER_MSG[用户消息]
        FILES[附件文件]
        CONTEXT[历史上下文]
    end

    subgraph "处理流"
        PREP[prepare_user_prompt]
        SDK[Claude SDK Client]
        TRANSPORT[E2BSandboxTransport]
    end

    subgraph "CLI 处理"
        CLI_IN[stdin JSON]
        INFERENCE[AI 推理]
        TOOL_EXEC[工具执行]
        CLI_OUT[stdout JSON]
    end

    subgraph "输出流"
        PARSE[解析 ANSI/JSON]
        PROCESS[StreamProcessor]
        REDIS[(Redis Stream)]
        SSE[SSE Response]
        DB[(Message.content)]
    end

    USER_MSG --> PREP
    FILES --> PREP
    CONTEXT --> PREP
    PREP --> SDK
    SDK --> TRANSPORT
    TRANSPORT --> CLI_IN
    CLI_IN --> INFERENCE
    INFERENCE --> TOOL_EXEC
    TOOL_EXEC --> CLI_OUT
    CLI_OUT --> PARSE
    PARSE --> PROCESS
    PROCESS --> REDIS
    PROCESS --> DB
    REDIS --> SSE
```

### 2.4 Transport 层实现细节

```mermaid
classDiagram
    class Transport {
        <<interface>>
        +connect() async
        +disconnect() async
        +write(data: bytes) async
        +read_messages() AsyncIterator
    }

    class E2BSandboxTransport {
        -sandbox: AsyncSandbox
        -process: Process
        -output_queue: asyncio.Queue
        -monitor_task: asyncio.Task
        -connected: bool
        +connect() async
        +disconnect() async
        +write(data: bytes) async
        +read_messages() AsyncIterator
        -_build_command() str
        -_parse_cli_output(line: str) dict|None
        -_monitor_process() async
        -_handle_stdout(data: bytes) async
        -_handle_stderr(data: bytes) async
    }

    class AsyncSandbox {
        +id: str
        +files: FilesModule
        +commands: CommandsModule
        +process: ProcessModule
        +connect() async AsyncSandbox
        +create() async AsyncSandbox
    }

    Transport <|.. E2BSandboxTransport
    E2BSandboxTransport --> AsyncSandbox
```

**关键实现点**:

```python
# 1. 命令构建
def _build_command(self) -> str:
    return " ".join([
        "claude",
        "--output-format", "stream-json",
        "--verbose",
        "--append-system-prompt", quote(self.system_prompt),
        "--permission-mode", self.permission_mode,
        "--model", self.model_id,
        "--mcp-config", quote(json.dumps(self.mcp_config)),
        "--input-format", "stream-json",
        *(["--resume", self.session_id] if self.session_id else []),
    ])

# 2. 输出解析
def _parse_cli_output(self, line: str) -> dict | None:
    # 去除 ANSI 转义码
    clean_line = ANSI_ESCAPE_PATTERN.sub("", line).strip()
    if not clean_line:
        return None
    try:
        return json.loads(clean_line)
    except json.JSONDecodeError:
        logger.debug(f"Non-JSON line: {clean_line}")
        return None

# 3. 异步消息读取
async def read_messages(self) -> AsyncIterator[dict]:
    while self.connected:
        try:
            message = await asyncio.wait_for(
                self.output_queue.get(),
                timeout=0.1
            )
            yield message
        except asyncio.TimeoutError:
            if not self.connected:
                break
```

---

## 3. 架构设计问题分析

### 3.1 问题一：紧耦合的服务依赖

```mermaid
graph TD
    subgraph "当前设计 - 紧耦合"
        CAS1[ClaudeAgentService]
        SS1[SandboxService]
        ET1[E2BSandboxTransport]

        CAS1 -->|直接依赖| SS1
        CAS1 -->|直接依赖| ET1
        SS1 -->|E2B SDK| E2B1[E2B API]
        ET1 -->|E2B SDK| E2B1
    end

    subgraph "理想设计 - 松耦合"
        CAS2[ClaudeAgentService]
        ISS[ISandboxService<br/>接口]
        ITR[ITransport<br/>接口]

        CAS2 -->|依赖接口| ISS
        CAS2 -->|依赖接口| ITR

        SS2[E2BSandboxService]
        ET2[E2BTransport]
        LOCAL[LocalSandboxService]
        LT[LocalTransport]

        ISS -.->|实现| SS2
        ISS -.->|实现| LOCAL
        ITR -.->|实现| ET2
        ITR -.->|实现| LT
    end

    style CAS1 fill:#fcc
    style CAS2 fill:#cfc
```

**问题**:
- `ClaudeAgentService` 直接依赖具体的 `SandboxService` 和 `E2BSandboxTransport`
- 无法轻松切换到其他沙箱提供商（如 Fly.io, Modal）
- 单元测试需要 mock 大量具体实现

**影响**:
- 供应商锁定风险
- 测试复杂度高
- 扩展困难

### 3.2 问题二：同步阻塞的权限审批

```mermaid
sequenceDiagram
    participant CLI as Claude CLI
    participant PS as Permission Server
    participant API as Backend API
    participant User as 用户

    Note over CLI,User: 当前设计 - 同步阻塞

    CLI->>PS: 请求权限
    PS->>API: HTTP POST (阻塞等待)

    rect rgb(255, 200, 200)
        Note over PS: 阻塞等待用户响应<br/>可能超时！
        API-->>User: 推送权限请求
        User-->>API: 用户响应 (可能很慢)
    end

    API-->>PS: 返回决定
    PS-->>CLI: 权限结果
```

**问题**:
- Permission Server 使用同步 HTTP 请求等待用户决定
- 用户可能需要很长时间才能响应
- 长时间等待可能导致连接超时

**影响**:
- 用户体验差（必须快速响应）
- 系统可靠性降低
- 可能导致整个会话失败

### 3.3 问题三：单点故障风险

```mermaid
graph TB
    subgraph "单点故障场景"
        USER[用户请求]
        CELERY[单个 Celery Task]
        E2B[E2B 连接]
        CLI[Claude CLI]

        USER --> CELERY
        CELERY --> E2B
        E2B --> CLI
    end

    subgraph "故障影响"
        F1[E2B 连接断开]
        F2[CLI 进程崩溃]
        F3[Celery Worker 死亡]

        F1 --> FAIL[整个会话失败]
        F2 --> FAIL
        F3 --> FAIL
    end

    style FAIL fill:#f66
```

**问题**:
- 一个 Celery Task 处理整个会话
- E2B 连接断开无自动重连
- Claude CLI 崩溃无恢复机制

**影响**:
- 长时间会话容易中断
- 用户需要重新开始
- 资源浪费

### 3.4 问题四：检查点恢复的局限性

```mermaid
flowchart TD
    subgraph "检查点创建"
        MSG[消息完成]
        RSYNC[rsync 增量备份]
        SAVE[保存 checkpoint_id]
    end

    subgraph "恢复场景"
        R1[用户请求恢复]
        R2[查找 checkpoint]
        R3{检查点存在?}
        R4[rsync 恢复文件]
        R5[恢复失败]
    end

    MSG --> RSYNC --> SAVE

    R1 --> R2 --> R3
    R3 -->|是| R4
    R3 -->|否| R5

    subgraph "问题"
        P1[只恢复文件系统]
        P2[不恢复进程状态]
        P3[不恢复网络连接]
        P4[不恢复环境变量修改]
    end

    R4 --> P1
    R4 --> P2
    R4 --> P3
    R4 --> P4

    style P1 fill:#fcc
    style P2 fill:#fcc
    style P3 fill:#fcc
    style P4 fill:#fcc
```

**问题**:
- 检查点只包含文件系统快照
- 无法恢复运行中的进程状态
- 无法恢复动态环境变量修改

**影响**:
- 恢复后状态不完整
- 某些操作无法继续

### 3.5 问题五：资源清理的竞态条件

```mermaid
sequenceDiagram
    participant Task as Celery Task
    participant SS as SandboxService
    participant E2B as E2B API

    Task->>SS: 处理消息中...

    Note over Task: 用户取消请求

    par 竞态条件
        Task->>SS: 尝试清理资源
        SS->>E2B: disconnect()
    and
        Task->>SS: 创建检查点 (可能仍在执行)
        SS->>E2B: 文件操作
    end

    Note over SS,E2B: 可能导致:<br/>- 部分清理<br/>- 检查点不完整<br/>- 资源泄漏
```

**问题**:
- 取消操作和清理操作可能同时进行
- 没有明确的资源锁定机制
- 检查点创建可能在不一致状态下执行

### 3.6 问题六：日志和可观测性不足

```mermaid
graph TB
    subgraph "当前状态"
        LOG1[分散的 print/logger]
        LOG2[缺乏结构化日志]
        LOG3[没有分布式追踪]
    end

    subgraph "影响"
        I1[调试困难]
        I2[问题定位慢]
        I3[性能分析难]
    end

    LOG1 --> I1
    LOG2 --> I2
    LOG3 --> I3

    style LOG1 fill:#fcc
    style LOG2 fill:#fcc
    style LOG3 fill:#fcc
```

**问题**:
- 缺乏统一的日志格式
- 没有请求级别的追踪 ID
- 难以关联跨服务的日志

---

## 4. 优化建议

### 4.1 引入接口抽象层

```mermaid
graph TB
    subgraph "新增抽象层"
        ISandbox[ISandboxProvider<br/>接口]
        ITransport[ITransport<br/>接口]
        IPermission[IPermissionHandler<br/>接口]
    end

    subgraph "E2B 实现"
        E2BProvider[E2BSandboxProvider]
        E2BTransport[E2BSandboxTransport]
    end

    subgraph "本地实现 (可选)"
        LocalProvider[LocalSandboxProvider]
        LocalTransport[LocalTransport]
    end

    subgraph "核心服务"
        CAS[ClaudeAgentService]
    end

    ISandbox -.-> E2BProvider
    ISandbox -.-> LocalProvider
    ITransport -.-> E2BTransport
    ITransport -.-> LocalTransport

    CAS --> ISandbox
    CAS --> ITransport

    style ISandbox fill:#9f9
    style ITransport fill:#9f9
```

### 4.2 异步权限审批

```mermaid
sequenceDiagram
    participant CLI as Claude CLI
    participant PS as Permission Server
    participant REDIS as Redis
    participant API as Backend API
    participant User as 用户

    Note over CLI,User: 优化设计 - 异步非阻塞

    CLI->>PS: 请求权限
    PS->>REDIS: 发布权限请求
    PS-->>CLI: 返回 "pending"

    CLI->>CLI: 暂停当前工具，继续其他处理

    par 异步处理
        REDIS-->>API: 订阅权限请求
        API-->>User: SSE 推送
        User-->>API: 用户响应
        API->>REDIS: 发布决定
    end

    PS->>REDIS: 轮询/订阅结果
    REDIS-->>PS: 返回决定
    PS-->>CLI: 恢复执行
```

### 4.3 会话弹性机制

```mermaid
flowchart TD
    subgraph "弹性设计"
        CONNECT[建立连接]
        HEARTBEAT[心跳检测]
        DETECT{检测到断开?}
        RECONNECT[自动重连]
        RESUME[恢复会话]
        NOTIFY[通知用户]
    end

    CONNECT --> HEARTBEAT
    HEARTBEAT --> DETECT
    DETECT -->|是| RECONNECT
    DETECT -->|否| HEARTBEAT
    RECONNECT -->|成功| RESUME
    RECONNECT -->|失败 3 次| NOTIFY
    RESUME --> HEARTBEAT
```

### 4.4 完整状态检查点

```python
# 建议的检查点结构
class FullCheckpoint:
    file_system: FileSystemSnapshot    # 文件系统快照
    environment: Dict[str, str]        # 环境变量
    session_state: SessionState        # Claude 会话状态
    process_state: Optional[ProcessState]  # 进程状态（如果可行）
    timestamp: datetime
    message_id: str

    async def restore(self, sandbox: Sandbox):
        await self._restore_files(sandbox)
        await self._restore_environment(sandbox)
        # Claude --resume 处理会话恢复
```

### 4.5 结构化日志和追踪

```python
# 建议的日志结构
@dataclass
class RequestContext:
    trace_id: str
    user_id: str
    chat_id: str
    message_id: str

def log_event(ctx: RequestContext, event: str, data: dict):
    logger.info(json.dumps({
        "trace_id": ctx.trace_id,
        "user_id": ctx.user_id,
        "chat_id": ctx.chat_id,
        "message_id": ctx.message_id,
        "event": event,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }))
```

### 4.6 优先级排序

| 优先级 | 问题 | 优化建议 | 影响 |
|--------|------|----------|------|
| **P0** | 权限审批阻塞 | 异步权限机制 | 用户体验 |
| **P0** | 单点故障 | 会话弹性机制 | 可靠性 |
| **P1** | 紧耦合 | 接口抽象层 | 可维护性 |
| **P1** | 日志不足 | 结构化日志 | 可观测性 |
| **P2** | 检查点局限 | 完整状态检查点 | 恢复能力 |
| **P2** | 竞态条件 | 资源锁定机制 | 数据一致性 |

---

## 总结

本系统采用了现代化的微服务架构，将 AI 能力（Claude）、安全执行（E2B 沙箱）和用户界面有机结合。核心设计亮点包括：

1. **分层清晰**: API → Service → Infrastructure 三层分明
2. **异步优先**: 全栈异步处理，Celery 后台任务
3. **实时通信**: SSE + WebSocket 支持流式响应
4. **安全隔离**: E2B 沙箱提供完全隔离的执行环境

但同时也存在需要改进的地方：

1. **供应商耦合**: 需要抽象层支持多沙箱提供商
2. **容错能力**: 需要更强的会话恢复和重连机制
3. **可观测性**: 需要统一的日志和追踪系统

通过实施上述优化建议，可以显著提升系统的可靠性、可维护性和用户体验。
