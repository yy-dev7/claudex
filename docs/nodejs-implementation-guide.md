# Node.js 技术栈实现指南

## 1. 概述

本文档基于现有 Python 架构分析，提供使用 Node.js 重新实现核心功能的技术方案。

## 2. 技术栈对比

### 2.1 Python vs Node.js 技术栈映射

| 功能 | Python 技术栈 | Node.js 技术栈 |
|------|---------------|----------------|
| **Web 框架** | FastAPI | NestJS / Fastify |
| **异步任务** | Celery + Redis | BullMQ + Redis |
| **数据库 ORM** | SQLAlchemy (async) | Prisma / TypeORM / Drizzle |
| **数据库** | PostgreSQL | PostgreSQL |
| **缓存/消息** | Redis (aioredis) | ioredis |
| **WebSocket** | FastAPI WebSocket | Socket.io / ws |
| **SSE** | sse-starlette | 原生 / @nestjs/event-emitter |
| **类型检查** | Pydantic + mypy | TypeScript + Zod |
| **E2B SDK** | e2b (Python) | @e2b/code-interpreter |
| **Claude SDK** | claude-agent-sdk | @anthropic-ai/claude-code |

### 2.2 推荐技术栈

```mermaid
graph TB
    subgraph "Frontend (保持不变)"
        REACT[React + TypeScript]
        VITE[Vite]
        ZUSTAND[Zustand]
        RQ[React Query]
    end

    subgraph "Backend (Node.js)"
        NEST[NestJS]
        PRISMA[Prisma ORM]
        BULLMQ[BullMQ]
        IOREDIS[ioredis]
    end

    subgraph "Infrastructure"
        PG[(PostgreSQL)]
        REDIS[(Redis)]
        E2B[E2B Sandbox]
    end

    REACT --> NEST
    NEST --> PRISMA
    NEST --> BULLMQ
    BULLMQ --> IOREDIS
    PRISMA --> PG
    IOREDIS --> REDIS
    NEST --> E2B
```

## 3. 核心模块实现

### 3.1 项目结构

```
backend/
├── src/
│   ├── main.ts                     # 入口文件
│   ├── app.module.ts               # 根模块
│   │
│   ├── modules/
│   │   ├── auth/                   # 认证模块
│   │   │   ├── auth.module.ts
│   │   │   ├── auth.controller.ts
│   │   │   ├── auth.service.ts
│   │   │   └── strategies/
│   │   │
│   │   ├── chat/                   # 聊天模块
│   │   │   ├── chat.module.ts
│   │   │   ├── chat.controller.ts
│   │   │   ├── chat.service.ts
│   │   │   └── processors/
│   │   │       └── chat.processor.ts
│   │   │
│   │   ├── sandbox/                # 沙箱模块
│   │   │   ├── sandbox.module.ts
│   │   │   ├── sandbox.service.ts
│   │   │   └── e2b-transport.ts
│   │   │
│   │   ├── claude-agent/           # Claude Agent 模块
│   │   │   ├── claude-agent.module.ts
│   │   │   ├── claude-agent.service.ts
│   │   │   └── stream-processor.ts
│   │   │
│   │   └── message/                # 消息模块
│   │       ├── message.module.ts
│   │       └── message.service.ts
│   │
│   ├── common/
│   │   ├── decorators/
│   │   ├── guards/
│   │   ├── interceptors/
│   │   └── pipes/
│   │
│   └── prisma/
│       ├── prisma.module.ts
│       ├── prisma.service.ts
│       └── schema.prisma
│
├── package.json
├── tsconfig.json
└── docker-compose.yml
```

### 3.2 核心依赖

```json
{
  "dependencies": {
    // Web 框架
    "@nestjs/common": "^10.0.0",
    "@nestjs/core": "^10.0.0",
    "@nestjs/platform-fastify": "^10.0.0",
    "@nestjs/websockets": "^10.0.0",
    "@nestjs/passport": "^10.0.0",

    // 数据库
    "@prisma/client": "^5.0.0",
    "prisma": "^5.0.0",

    // 任务队列
    "@nestjs/bullmq": "^10.0.0",
    "bullmq": "^5.0.0",

    // Redis
    "ioredis": "^5.0.0",

    // E2B
    "@e2b/code-interpreter": "^0.0.10",

    // Claude
    "@anthropic-ai/claude-code": "^0.1.0",

    // 工具库
    "zod": "^3.22.0",
    "uuid": "^9.0.0",
    "rxjs": "^7.8.0"
  }
}
```

## 4. 核心服务实现

### 4.1 沙箱服务 (SandboxService)

```typescript
// src/modules/sandbox/sandbox.service.ts
import { Injectable, Logger } from '@nestjs/common';
import { Sandbox } from '@e2b/code-interpreter';

@Injectable()
export class SandboxService {
  private readonly logger = new Logger(SandboxService.name);
  private sandboxes = new Map<string, Sandbox>();

  async createSandbox(): Promise<string> {
    const sandbox = await Sandbox.create({
      template: process.env.E2B_TEMPLATE_ID,
      apiKey: process.env.E2B_API_KEY,
      timeout: 3600 * 1000, // 1 hour
    });

    this.sandboxes.set(sandbox.id, sandbox);
    return sandbox.id;
  }

  async getOrConnect(sandboxId: string): Promise<Sandbox> {
    if (this.sandboxes.has(sandboxId)) {
      return this.sandboxes.get(sandboxId)!;
    }

    const sandbox = await Sandbox.connect({
      sandboxId,
      apiKey: process.env.E2B_API_KEY,
    });

    this.sandboxes.set(sandboxId, sandbox);
    return sandbox;
  }

  async executeCommand(
    sandboxId: string,
    command: string,
    options?: { background?: boolean }
  ): Promise<{ stdout: string; stderr: string; exitCode: number }> {
    const sandbox = await this.getOrConnect(sandboxId);
    const result = await sandbox.commands.run(command);
    return {
      stdout: result.stdout,
      stderr: result.stderr,
      exitCode: result.exitCode,
    };
  }

  async writeFile(sandboxId: string, path: string, content: string): Promise<void> {
    const sandbox = await this.getOrConnect(sandboxId);
    await sandbox.files.write(path, content);
  }

  async readFile(sandboxId: string, path: string): Promise<string> {
    const sandbox = await this.getOrConnect(sandboxId);
    return await sandbox.files.read(path);
  }

  async initializeSandbox(
    sandboxId: string,
    config: {
      envVars?: Record<string, string>;
      githubToken?: string;
      skills?: Array<{ name: string; content: string }>;
    }
  ): Promise<void> {
    const sandbox = await this.getOrConnect(sandboxId);

    // 启动 OpenVSCode Server
    await sandbox.commands.run(
      'code-server --port 8765 --auth none &',
      { background: true }
    );

    // 设置环境变量
    if (config.envVars) {
      const envContent = Object.entries(config.envVars)
        .map(([k, v]) => `export ${k}="${v}"`)
        .join('\n');
      await sandbox.files.write('/home/user/.env', envContent);
    }

    // 配置 GitHub
    if (config.githubToken) {
      await sandbox.commands.run(
        `git config --global credential.helper store`
      );
      await sandbox.files.write(
        '/home/user/.git-credentials',
        `https://oauth2:${config.githubToken}@github.com`
      );
    }

    // 复制 Skills
    if (config.skills?.length) {
      await sandbox.commands.run('mkdir -p /home/user/.claude/skills');
      for (const skill of config.skills) {
        await sandbox.files.write(
          `/home/user/.claude/skills/${skill.name}.md`,
          skill.content
        );
      }
    }
  }

  async deleteSandbox(sandboxId: string): Promise<void> {
    const sandbox = this.sandboxes.get(sandboxId);
    if (sandbox) {
      await sandbox.kill();
      this.sandboxes.delete(sandboxId);
    }
  }
}
```

### 4.2 E2B Transport 实现

```typescript
// src/modules/sandbox/e2b-transport.ts
import { Sandbox, ProcessHandle } from '@e2b/code-interpreter';
import { EventEmitter } from 'events';

interface TransportOptions {
  model: string;
  systemPrompt?: string;
  permissionMode: 'plan' | 'ask' | 'auto';
  mcpServers?: Record<string, McpServerConfig>;
  resume?: string;
  env?: Record<string, string>;
}

interface McpServerConfig {
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

export class E2BSandboxTransport extends EventEmitter {
  private sandbox: Sandbox;
  private process: ProcessHandle | null = null;
  private connected = false;
  private outputBuffer: string[] = [];

  constructor(
    private readonly sandboxId: string,
    private readonly options: TransportOptions,
    private readonly apiKey: string
  ) {
    super();
  }

  async connect(): Promise<void> {
    // 连接沙箱
    this.sandbox = await Sandbox.connect({
      sandboxId: this.sandboxId,
      apiKey: this.apiKey,
    });

    // 构建 CLI 命令
    const command = this.buildCommand();

    // 启动 Claude CLI
    this.process = await this.sandbox.commands.run(command, {
      envs: {
        CLAUDE_CODE_ENTRYPOINT: 'sdk-js',
        PYTHONUNBUFFERED: '1',
        ...this.options.env,
      },
      onStdout: (data) => this.handleStdout(data),
      onStderr: (data) => this.handleStderr(data),
    });

    this.connected = true;
  }

  private buildCommand(): string {
    const parts = ['claude', '--output-format', 'stream-json', '--verbose'];

    if (this.options.model) {
      parts.push('--model', this.options.model);
    }

    if (this.options.permissionMode) {
      parts.push('--permission-mode', this.options.permissionMode);
    }

    if (this.options.systemPrompt) {
      parts.push('--append-system-prompt', JSON.stringify(this.options.systemPrompt));
    }

    if (this.options.mcpServers) {
      const mcpConfig = JSON.stringify({ mcpServers: this.options.mcpServers });
      parts.push('--mcp-config', mcpConfig);
    }

    if (this.options.resume) {
      parts.push('--resume', this.options.resume);
    }

    parts.push('--input-format', 'stream-json');

    return parts.map(p => p.includes(' ') ? `"${p}"` : p).join(' ');
  }

  private handleStdout(data: string): void {
    // 去除 ANSI 转义码
    const cleanData = data.replace(/\x1b\[[0-9;]*m/g, '');

    // 按行分割处理
    const lines = cleanData.split('\n');
    for (const line of lines) {
      if (!line.trim()) continue;

      try {
        const parsed = JSON.parse(line);
        this.emit('message', parsed);
      } catch {
        // 非 JSON 行，记录日志
        this.emit('log', line);
      }
    }
  }

  private handleStderr(data: string): void {
    this.emit('error', data);
  }

  async write(data: object): Promise<void> {
    if (!this.process) {
      throw new Error('Transport not connected');
    }

    const jsonData = JSON.stringify(data) + '\n';
    await this.sandbox.commands.sendStdin(this.process.pid, jsonData);
  }

  async* readMessages(): AsyncGenerator<Record<string, unknown>> {
    const messageQueue: Record<string, unknown>[] = [];
    let resolveNext: ((value: Record<string, unknown>) => void) | null = null;

    const messageHandler = (msg: Record<string, unknown>) => {
      if (resolveNext) {
        resolveNext(msg);
        resolveNext = null;
      } else {
        messageQueue.push(msg);
      }
    };

    this.on('message', messageHandler);

    try {
      while (this.connected) {
        if (messageQueue.length > 0) {
          yield messageQueue.shift()!;
        } else {
          yield await new Promise<Record<string, unknown>>((resolve) => {
            resolveNext = resolve;
          });
        }
      }
    } finally {
      this.off('message', messageHandler);
    }
  }

  async disconnect(): Promise<void> {
    if (this.process) {
      // 发送 EOF
      await this.sandbox.commands.sendStdin(this.process.pid, '\x04');
    }
    this.connected = false;
  }
}
```

### 4.3 Claude Agent 服务

```typescript
// src/modules/claude-agent/claude-agent.service.ts
import { Injectable, Logger } from '@nestjs/common';
import { SandboxService } from '../sandbox/sandbox.service';
import { E2BSandboxTransport } from '../sandbox/e2b-transport';
import { StreamProcessor, StreamEvent } from './stream-processor';

interface AgentOptions {
  chatId: string;
  sandboxId: string;
  model: string;
  systemPrompt?: string;
  permissionMode: 'plan' | 'ask' | 'auto';
  sessionId?: string;
  envVars?: Record<string, string>;
  mcpServers?: Record<string, unknown>;
}

@Injectable()
export class ClaudeAgentService {
  private readonly logger = new Logger(ClaudeAgentService.name);

  constructor(private readonly sandboxService: SandboxService) {}

  async *getAiStream(
    prompt: string,
    options: AgentOptions
  ): AsyncGenerator<StreamEvent> {
    const transport = new E2BSandboxTransport(
      options.sandboxId,
      {
        model: options.model,
        systemPrompt: options.systemPrompt,
        permissionMode: options.permissionMode,
        mcpServers: options.mcpServers as Record<string, unknown>,
        resume: options.sessionId,
        env: options.envVars,
      },
      process.env.E2B_API_KEY!
    );

    try {
      // 连接并启动 CLI
      await transport.connect();

      // 发送用户消息
      await transport.write({
        type: 'user_message',
        content: [{ type: 'text', text: prompt }],
      });

      // 处理响应流
      const processor = new StreamProcessor();

      for await (const message of transport.readMessages()) {
        const events = processor.processMessage(message);
        for (const event of events) {
          yield event;
        }

        // 检查是否完成
        if (message.type === 'result') {
          break;
        }
      }
    } finally {
      await transport.disconnect();
    }
  }

  buildMcpServers(
    chatId: string,
    permissionMode: string,
    customMcps?: Record<string, unknown>
  ): Record<string, unknown> {
    const servers: Record<string, unknown> = {};

    // Permission Server
    servers['permission'] = {
      command: 'python3',
      args: ['-u', '/usr/local/bin/permission_server.py'],
      env: {
        API_BASE_URL: process.env.BASE_URL,
        CHAT_ID: chatId,
        PERMISSION_MODE: permissionMode,
      },
    };

    // 合并自定义 MCP
    if (customMcps) {
      Object.assign(servers, customMcps);
    }

    return servers;
  }
}
```

### 4.4 流处理器

```typescript
// src/modules/claude-agent/stream-processor.ts

export type StreamEventType =
  | 'assistant_text'
  | 'assistant_thinking'
  | 'tool_started'
  | 'tool_completed'
  | 'tool_failed'
  | 'system';

export interface StreamEvent {
  type: StreamEventType;
  [key: string]: unknown;
}

interface ToolState {
  id: string;
  name: string;
  input: Record<string, unknown>;
  startedAt: Date;
}

export class StreamProcessor {
  private activeTools = new Map<string, ToolState>();

  processMessage(message: Record<string, unknown>): StreamEvent[] {
    const events: StreamEvent[] = [];

    switch (message.type) {
      case 'assistant':
        events.push(...this.processAssistantMessage(message));
        break;

      case 'result':
        events.push(...this.processResultMessage(message));
        break;

      case 'system':
        events.push({ type: 'system', message: message.message });
        break;
    }

    return events;
  }

  private processAssistantMessage(message: Record<string, unknown>): StreamEvent[] {
    const events: StreamEvent[] = [];
    const content = message.content as Array<Record<string, unknown>>;

    for (const block of content) {
      switch (block.type) {
        case 'text':
          events.push({
            type: 'assistant_text',
            text: block.text as string,
          });
          break;

        case 'thinking':
          events.push({
            type: 'assistant_thinking',
            thinking: block.thinking as string,
          });
          break;

        case 'tool_use':
          const toolId = block.id as string;
          this.activeTools.set(toolId, {
            id: toolId,
            name: block.name as string,
            input: block.input as Record<string, unknown>,
            startedAt: new Date(),
          });
          events.push({
            type: 'tool_started',
            tool: {
              id: toolId,
              name: block.name,
              input: block.input,
            },
          });
          break;

        case 'tool_result':
          const resultToolId = block.tool_use_id as string;
          const tool = this.activeTools.get(resultToolId);
          if (tool) {
            const isError = block.is_error as boolean;
            events.push({
              type: isError ? 'tool_failed' : 'tool_completed',
              tool: {
                id: resultToolId,
                name: tool.name,
                result: this.normalizeResult(block.content),
                error: isError ? block.content : undefined,
              },
            });
            this.activeTools.delete(resultToolId);
          }
          break;
      }
    }

    return events;
  }

  private processResultMessage(message: Record<string, unknown>): StreamEvent[] {
    // 处理最终结果
    return this.processAssistantMessage(message);
  }

  private normalizeResult(content: unknown): unknown {
    if (typeof content === 'string') {
      try {
        return JSON.parse(content);
      } catch {
        return content;
      }
    }
    return content;
  }
}
```

### 4.5 聊天处理器 (BullMQ)

```typescript
// src/modules/chat/processors/chat.processor.ts
import { Processor, WorkerHost } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import { Injectable, Logger } from '@nestjs/common';
import { ClaudeAgentService } from '../../claude-agent/claude-agent.service';
import { MessageService } from '../../message/message.service';
import { Redis } from 'ioredis';
import { InjectRedis } from '@nestjs-modules/ioredis';

interface ChatJobData {
  chatId: string;
  messageId: string;
  prompt: string;
  sandboxId: string;
  model: string;
  systemPrompt?: string;
  permissionMode: 'plan' | 'ask' | 'auto';
  sessionId?: string;
  envVars?: Record<string, string>;
}

@Processor('chat')
@Injectable()
export class ChatProcessor extends WorkerHost {
  private readonly logger = new Logger(ChatProcessor.name);

  constructor(
    private readonly claudeAgentService: ClaudeAgentService,
    private readonly messageService: MessageService,
    @InjectRedis() private readonly redis: Redis
  ) {
    super();
  }

  async process(job: Job<ChatJobData>): Promise<void> {
    const { chatId, messageId, prompt, ...options } = job.data;
    const events: unknown[] = [];

    try {
      // 更新消息状态为处理中
      await this.messageService.updateStatus(messageId, 'in_progress');

      // 获取 AI 流
      const stream = this.claudeAgentService.getAiStream(prompt, {
        chatId,
        ...options,
      });

      // 处理流事件
      for await (const event of stream) {
        events.push(event);

        // 发布到 Redis Stream
        await this.redis.xadd(
          `chat:${chatId}:stream`,
          '*',
          'event',
          JSON.stringify(event)
        );

        // 检查取消信号
        const cancelled = await this.redis.get(`chat:${chatId}:cancel`);
        if (cancelled) {
          this.logger.log(`Chat ${chatId} cancelled by user`);
          break;
        }
      }

      // 保存消息内容
      await this.messageService.update(messageId, {
        content: JSON.stringify(events),
        status: 'completed',
      });

    } catch (error) {
      this.logger.error(`Error processing chat ${chatId}:`, error);

      await this.messageService.update(messageId, {
        content: JSON.stringify(events),
        status: 'failed',
      });

      throw error;
    }
  }
}
```

### 4.6 聊天控制器 (SSE)

```typescript
// src/modules/chat/chat.controller.ts
import {
  Controller,
  Post,
  Get,
  Body,
  Param,
  Sse,
  UseGuards,
  Req,
} from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { map } from 'rxjs/operators';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { ChatService } from './chat.service';
import { Redis } from 'ioredis';
import { InjectRedis } from '@nestjs-modules/ioredis';

interface MessageEvent {
  data: string;
  id?: string;
  type?: string;
}

@Controller('api/v1/chat')
@UseGuards(JwtAuthGuard)
export class ChatController {
  constructor(
    private readonly chatService: ChatService,
    @InjectRedis() private readonly redis: Redis
  ) {}

  @Post()
  async sendMessage(
    @Req() req: { user: { id: string } },
    @Body() body: {
      prompt: string;
      chatId?: string;
      model: string;
      permissionMode?: 'plan' | 'ask' | 'auto';
    }
  ) {
    const { prompt, chatId, model, permissionMode = 'auto' } = body;
    const userId = req.user.id;

    // 创建或获取聊天
    const chat = chatId
      ? await this.chatService.getChat(chatId, userId)
      : await this.chatService.createChat(userId);

    // 创建消息并入队任务
    const message = await this.chatService.sendMessage({
      chatId: chat.id,
      prompt,
      model,
      permissionMode,
    });

    return {
      chatId: chat.id,
      messageId: message.id,
    };
  }

  @Sse(':chatId/stream')
  stream(@Param('chatId') chatId: string): Observable<MessageEvent> {
    const subject = new Subject<MessageEvent>();

    // 订阅 Redis Stream
    const streamKey = `chat:${chatId}:stream`;
    let lastId = '0';

    const poll = async () => {
      try {
        const results = await this.redis.xread(
          'BLOCK',
          1000,
          'STREAMS',
          streamKey,
          lastId
        );

        if (results) {
          for (const [, messages] of results) {
            for (const [id, fields] of messages) {
              lastId = id;
              const event = JSON.parse(fields[1]);
              subject.next({
                data: JSON.stringify(event),
                id,
              });
            }
          }
        }

        // 继续轮询
        if (!subject.closed) {
          setImmediate(poll);
        }
      } catch (error) {
        subject.error(error);
      }
    };

    poll();

    return subject.pipe(
      map((event) => ({
        data: event.data,
        id: event.id,
        type: 'message',
      }))
    );
  }

  @Post(':chatId/cancel')
  async cancelStream(@Param('chatId') chatId: string) {
    await this.redis.set(`chat:${chatId}:cancel`, '1', 'EX', 60);
    return { success: true };
  }
}
```

## 5. 数据库 Schema (Prisma)

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id             String        @id @default(uuid())
  email          String        @unique
  username       String        @unique
  hashedPassword String        @map("hashed_password")
  oauthProvider  String?       @map("oauth_provider")
  createdAt      DateTime      @default(now()) @map("created_at")
  updatedAt      DateTime      @updatedAt @map("updated_at")

  chats    Chat[]
  settings UserSettings?

  @@map("users")
}

model UserSettings {
  id                       String  @id @default(uuid())
  userId                   String  @unique @map("user_id")
  e2bApiKey                String? @map("e2b_api_key")
  claudeCodeOauthToken     String? @map("claude_code_oauth_token")
  githubPersonalAccessToken String? @map("github_personal_access_token")
  customEnvVars            Json?   @map("custom_env_vars")
  customMcps               Json?   @map("custom_mcps")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@map("user_settings")
}

model Chat {
  id                String    @id @default(uuid())
  title             String    @default("New Chat")
  userId            String    @map("user_id")
  sandboxId         String?   @map("sandbox_id")
  sessionId         String?   @map("session_id")
  contextTokenUsage Int       @default(0) @map("context_token_usage")
  pinnedAt          DateTime? @map("pinned_at")
  deletedAt         DateTime? @map("deleted_at")
  createdAt         DateTime  @default(now()) @map("created_at")
  updatedAt         DateTime  @updatedAt @map("updated_at")

  user     User      @relation(fields: [userId], references: [id], onDelete: Cascade)
  messages Message[]

  @@index([userId, deletedAt])
  @@map("chats")
}

model Message {
  id           String        @id @default(uuid())
  chatId       String        @map("chat_id")
  content      String        @db.Text
  role         MessageRole
  modelId      String?       @map("model_id")
  checkpointId String?       @map("checkpoint_id")
  sessionId    String?       @map("session_id")
  totalCostUsd Float         @default(0) @map("total_cost_usd")
  streamStatus StreamStatus  @default(IN_PROGRESS) @map("stream_status")
  deletedAt    DateTime?     @map("deleted_at")
  createdAt    DateTime      @default(now()) @map("created_at")
  updatedAt    DateTime      @updatedAt @map("updated_at")

  chat        Chat                @relation(fields: [chatId], references: [id], onDelete: Cascade)
  attachments MessageAttachment[]

  @@index([chatId, deletedAt])
  @@map("messages")
}

model MessageAttachment {
  id        String         @id @default(uuid())
  messageId String         @map("message_id")
  fileUrl   String         @map("file_url")
  filePath  String         @map("file_path")
  fileType  AttachmentType @map("file_type")
  filename  String?

  message Message @relation(fields: [messageId], references: [id], onDelete: Cascade)

  @@map("message_attachments")
}

enum MessageRole {
  USER      @map("user")
  ASSISTANT @map("assistant")
}

enum StreamStatus {
  IN_PROGRESS @map("in_progress")
  COMPLETED   @map("completed")
  FAILED      @map("failed")
  INTERRUPTED @map("interrupted")
}

enum AttachmentType {
  IMAGE @map("image")
  PDF   @map("pdf")
  XLSX  @map("xlsx")
}
```

## 6. 实现要点总结

### 6.1 关键差异

| 方面 | Python 实现 | Node.js 实现 |
|------|-------------|--------------|
| **异步模型** | asyncio | Event Loop + Promises |
| **任务队列** | Celery (进程隔离) | BullMQ (线程/Worker) |
| **ORM** | SQLAlchemy (显式 session) | Prisma (隐式连接) |
| **类型系统** | Pydantic + mypy | TypeScript + Zod |
| **DI 容器** | 手动/依赖注入 | NestJS IoC 容器 |

### 6.2 核心实现清单

- [x] E2B Transport 层实现
- [x] Claude Agent 服务封装
- [x] 流式事件处理器
- [x] BullMQ 任务处理器
- [x] Redis Stream SSE 分发
- [x] Prisma 数据模型

### 6.3 注意事项

1. **E2B SDK**: Node.js 版本是 `@e2b/code-interpreter`，API 略有不同
2. **Claude SDK**: 需要使用 `@anthropic-ai/claude-code`（如果可用）或自行实现 Transport
3. **流处理**: Node.js 使用 AsyncGenerator 需要注意内存管理
4. **Redis Stream**: 使用 XREAD BLOCK 实现长轮询
5. **类型安全**: 使用 Zod 进行运行时验证

### 6.4 性能优化建议

1. 使用 `fastify` 替代 `express` 提升 HTTP 性能
2. 使用 `ioredis` 的 pipeline 批量操作
3. 使用 Prisma 的 `$transaction` 批量数据库操作
4. 使用 `cluster` 模式充分利用多核 CPU
