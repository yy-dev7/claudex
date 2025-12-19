# Claudex

Open-source general AI agent powered by Claude Agent SDK with sandboxed code execution, in-browser IDE, and extensible capabilities.

**Try it live:** [claudex.pro](https://claudex.pro) — add your own API keys and start using it immediately.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg)](https://fastapi.tiangolo.com/)

## Screenshots

![Chat Interface](screenshots/chat-interface.png)

![Agent Workflow](screenshots/agent-workflow.png)

## Features

### Core Chat
- Real-time streaming responses via Server-Sent Events (SSE)
- Multiple Claude models (Haiku, Sonnet, Opus) via Anthropic, Z.AI, and OpenRouter
- Chat history with automatic title generation
- File attachments (images, PDFs, Excel files up to 5MB)
- Token usage tracking and context management

### Sandbox Code Execution
- Live code execution powered by [E2B](https://e2b.dev)
- Integrated VS Code editor in the browser
- Terminal access with full PTY support
- File system management and port forwarding
- Environment checkpoints and snapshots

### Claude Code Integration
- [Claude Agent SDK](https://github.com/anthropics/claude-code) integration for agentic workflows
- Tool use with streaming execution results
- Permission-based modes (plan, ask, auto)
- Extended thinking with configurable token allocation

### Extensibility
- **Custom Skills** - Extensible skill packages (ZIP format with YAML metadata)
- **Custom Agents** - Define agents with specific tool configurations
- **Slash Commands** - Built-in commands (`/context`, `/compact`, `/review`, `/init`)
- **MCP Support** - Model Context Protocol servers (NPX, BunX, UVX, HTTP)
- **Task Scheduling** - Automated recurring tasks with Celery

### Security
- JWT authentication with refresh tokens
- Encrypted credential storage (Fernet)
- Rate limiting and CORS protection
- Security headers (HSTS, CSP, X-Frame-Options)

## Quick Start

### Prerequisites

- Docker and Docker Compose

### Run

```bash
git clone https://github.com/Mng-dev-ai/claudex.git
cd claudex
docker compose up -d
```

Open http://localhost:3000

### Services

| Service | Port |
|---------|------|
| Frontend | 3000 |
| Backend API | 8080 |
| PostgreSQL | 5432 |
| Redis | 6379 |

## Configuration

All defaults work out of the box for development. For sandbox and AI features, configure these per-user in the settings UI:

| Setting | Description |
|---------|-------------|
| E2B API Key | [E2B](https://e2b.dev) sandbox API key for code execution |
| Claude OAuth Token | For Anthropic models via [Claude Code](https://claude.ai/code) |
| Z.AI API Key | For models via [Z.AI](https://z.ai) (Anthropic-compatible API) |
| OpenRouter API Key | For models via [OpenRouter](https://openrouter.ai) |

You only need one of the AI provider keys (Claude OAuth, Z.AI, or OpenRouter) depending on which models you want to use.

### Local Development with Permissions

The permission system uses an MCP server running inside the E2B sandbox that makes HTTP requests back to your backend API. Since E2B sandboxes run remotely, they cannot reach `localhost`.

For permission prompts to work locally, expose your backend via a tunnel:

```bash
# Using ngrok
ngrok http 8080

# Using Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8080
```

Then set the `BASE_URL` environment variable to your tunnel URL:

```bash
BASE_URL=https://your-tunnel-url.ngrok.io docker compose up -d
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│   FastAPI       │────▶│   PostgreSQL    │
│   React/Vite    │     │   Backend       │     │   Database      │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌───────────┐ ┌───────────┐ ┌───────────┐
            │   Redis   │ │  Celery   │ │    E2B    │
            │  Pub/Sub  │ │  Workers  │ │  Sandbox  │
            └───────────┘ └───────────┘ └───────────┘
```

### Key Patterns

- **SSE Streaming** - Real-time chat responses via Server-Sent Events
- **Redis Pub/Sub** - Cross-worker communication for streaming
- **Celery Tasks** - Background chat processing and task scheduling
- **JWT Auth** - Access tokens (15min) + refresh tokens (30 days)
- **Async SQLAlchemy** - Non-blocking database operations

## Tech Stack

### Frontend
- React 19 with TypeScript 5.7
- Vite for builds
- TailwindCSS for styling
- Zustand for state management
- React Query for server state
- Monaco Editor for code editing
- XTerm.js for terminal emulation

### Backend
- FastAPI with async/await
- Python 3.13
- SQLAlchemy 2.0 with async PostgreSQL
- Celery for background tasks
- Redis for caching and pub/sub
- Granian ASGI server

## Project Structure

```
claudex/
├── backend/
│   ├── app/
│   │   ├── api/endpoints/     # API route handlers
│   │   ├── core/              # Config, security, middleware
│   │   ├── models/
│   │   │   ├── db_models/     # SQLAlchemy ORM models
│   │   │   └── schemas/       # Pydantic schemas
│   │   ├── services/          # Business logic layer
│   │   ├── tasks/             # Celery background tasks
│   │   └── admin/             # SQLAdmin configuration
│   ├── migrations/            # Alembic migrations
│   └── tests/                 # Pytest test suite
├── frontend/
│   └── src/
│       ├── components/        # React components
│       │   ├── chat/          # Chat UI
│       │   ├── editor/        # Code editor
│       │   └── ui/            # Reusable primitives
│       ├── hooks/             # Custom React hooks
│       ├── pages/             # Route pages
│       ├── services/          # API clients
│       └── store/             # Zustand stores
└── docker-compose.yml
```

## Database Models

| Model | Description |
|-------|-------------|
| `User` | User accounts with profile data |
| `UserSettings` | API keys, preferences, custom configurations |
| `Chat` | Conversation containers |
| `Message` | Individual messages (user/assistant roles) |
| `MessageAttachment` | File attachments |
| `AIModel` | Available AI models with provider info |
| `ScheduledTask` | Recurring automated tasks |

## Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f api

# Run tests
docker compose -f docker-compose.test.yml run --rm backend-test pytest
```

## API Documentation

When running, access the API docs at http://localhost:8080/api/v1/docs

## Admin Panel

SQLAdmin panel for database management: http://localhost:8080/admin

Default credentials (seeded on first run):
- **Email:** `admin@example.com`
- **Password:** `admin123`

Use the admin panel to manage users, chats, and add AI models (Anthropic, Z.AI, OpenRouter).

To customize admin credentials, set environment variables before first run:
```bash
ADMIN_EMAIL=your@email.com ADMIN_USERNAME=yourusername ADMIN_PASSWORD=yourpassword docker compose up -d
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License

MIT - see [LICENSE](LICENSE)
