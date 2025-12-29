import asyncio
import errno
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.constants import PTY_INPUT_QUEUE_SIZE
from app.core.config import get_settings
from app.core.security import get_user_from_token
from app.db.session import SessionLocal
from sqlalchemy import select

from app.models.db_models import Chat, User
from app.services.exceptions import UserException
from app.services.sandbox import SandboxService
from app.services.sandbox_providers import (
    SandboxProviderType,
    create_sandbox_provider,
)
from app.services.user import UserService
from app.utils.queue import drain_queue, put_with_overflow

settings = get_settings()
router = APIRouter()
logger = logging.getLogger(__name__)


async def authenticate_user(token: str) -> tuple[User | None, str | None, str]:
    try:
        async with SessionLocal() as db:
            user = await get_user_from_token(token, db)
            if not user:
                return None, None, "docker"

            user_service = UserService(session_factory=SessionLocal)
            try:
                user_settings = await user_service.get_user_settings(user.id, db=db)
                e2b_api_key = user_settings.e2b_api_key
                sandbox_provider = user_settings.sandbox_provider
            except UserException:
                e2b_api_key = None
                sandbox_provider = "docker"

        return user, e2b_api_key, sandbox_provider

    except Exception as e:
        logger.warning("WebSocket authentication failed: %s", e)
        return None, None, "docker"


async def wait_for_auth(
    websocket: WebSocket, timeout: float = 10.0
) -> tuple[User | None, str | None, str]:
    try:
        message = await asyncio.wait_for(websocket.receive(), timeout=timeout)
    except asyncio.TimeoutError:
        return None, None, "docker"

    if "text" not in message:
        return None, None, "docker"

    try:
        data = json.loads(message["text"])
    except json.JSONDecodeError:
        return None, None, "docker"

    if data.get("type") != "auth":
        return None, None, "docker"

    token = data.get("token")
    if not token:
        return None, None, "docker"

    return await authenticate_user(token)


@dataclass
class TerminalSession:
    sandbox_service: SandboxService
    sandbox_id: str
    websocket: WebSocket
    pty_session: dict[str, Any] | None = None
    output_task: asyncio.Task[None] | None = None
    input_task: asyncio.Task[None] | None = None
    input_queue: asyncio.Queue[bytes] | None = None

    async def start(self, rows: int, cols: int) -> dict[str, Any]:
        await self.stop()

        self.pty_session = await self.sandbox_service.create_pty_session(
            self.sandbox_id, rows, cols
        )

        self.input_queue = asyncio.Queue(maxsize=PTY_INPUT_QUEUE_SIZE)
        self.input_task = asyncio.create_task(self.input_worker(self.pty_session["id"]))
        self.input_task.add_done_callback(self._handle_input_task_done)

        self.output_task = asyncio.create_task(
            self.sandbox_service.forward_pty_output(
                self.sandbox_id, self.pty_session["id"], self.websocket
            )
        )

        return self.pty_session

    def enqueue_input(self, data: Any) -> None:
        # Queue overflow handling: drops oldest input when full to ensure newest keystrokes
        # aren't lost. Double-try pattern handles race condition where another item may arrive
        # between get_nowait and put_nowait, causing the second put to also fail (silently ignored).
        if not self.pty_session or not self.input_queue:
            return

        if not isinstance(data, (bytes, bytearray)):
            return

        put_with_overflow(self.input_queue, bytes(data))

    async def resize(self, rows: int, cols: int) -> None:
        if not self.pty_session:
            return

        await self.sandbox_service.resize_pty_session(
            self.sandbox_id,
            self.pty_session["id"],
            rows,
            cols,
        )

    async def stop(self) -> None:
        if self.input_task:
            self.input_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.input_task
            self.input_task = None

        self.input_queue = None

        if self.output_task:
            self.output_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.output_task
            self.output_task = None

        if self.pty_session:
            await self.sandbox_service.cleanup_pty_session(
                self.sandbox_id, self.pty_session["id"]
            )
            self.pty_session = None

    async def close_websocket(self) -> None:
        try:
            await self.websocket.close()
        except OSError as exc:
            if exc.errno != errno.EPIPE:
                logger.error("Failed to close websocket cleanly: %s", exc)

    async def input_worker(self, session_id: str) -> None:
        # Batches queued input to reduce round-trips to the sandbox. After receiving the first
        # item, drains all immediately available items with get_nowait() and sends them together.
        # This improves performance for rapid typing or paste operations.
        if self.input_queue is None:
            return

        try:
            while True:
                buffer = await drain_queue(self.input_queue)
                payload = b"".join(buffer)
                await self.sandbox_service.send_pty_input(
                    self.sandbox_id, session_id, payload
                )
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _handle_input_task_done(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in input task: %s", e)


@router.websocket("/{sandbox_id}/terminal")
async def terminal_websocket(
    websocket: WebSocket,
    sandbox_id: str,
) -> None:
    await websocket.accept()

    user, e2b_api_key, user_sandbox_provider = await wait_for_auth(websocket)
    if not user:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    async with SessionLocal() as db:
        query = select(Chat.sandbox_provider).where(
            Chat.sandbox_id == sandbox_id,
            Chat.user_id == user.id,
            Chat.deleted_at.is_(None),
        )
        result = await db.execute(query)
        row = result.one_or_none()
        if not row:
            await websocket.close(code=4004, reason="Sandbox not found")
            return
        sandbox_provider_type = row.sandbox_provider or user_sandbox_provider

    if sandbox_provider_type == SandboxProviderType.E2B and not e2b_api_key:
        await websocket.close(
            code=4003,
            reason="E2B API key is required. Please configure your E2B API key in Settings.",
        )
        return

    provider = create_sandbox_provider(sandbox_provider_type, e2b_api_key)

    sandbox_service = SandboxService(provider)
    session = TerminalSession(sandbox_service, sandbox_id, websocket)

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            if "bytes" in message:
                session.enqueue_input(message["bytes"])
                continue

            if "text" not in message:
                continue

            try:
                data = json.loads(message["text"])
            except json.JSONDecodeError:
                continue

            data_type = data.get("type")

            if data_type == "init":
                rows = int(data.get("rows") or 24)
                cols = int(data.get("cols") or 80)

                pty_session = await session.start(rows, cols)

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "init",
                            "id": pty_session["id"],
                            "rows": pty_session["rows"],
                            "cols": pty_session["cols"],
                        }
                    )
                )

            elif data_type == "resize":
                rows = int(data.get("rows") or 0)
                cols = int(data.get("cols") or 0)
                await session.resize(rows, cols)
            elif data_type == "close":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Error in terminal websocket: %s", e)
    finally:
        await session.stop()
        await session.close_websocket()
        await sandbox_service.cleanup()
