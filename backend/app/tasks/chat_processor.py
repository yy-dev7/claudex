import asyncio
import json
import logging
import uuid
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from typing import AsyncIterator, Any

from celery.exceptions import Ignore
from redis.asyncio import Redis
from sqlalchemy import select

from app.constants import (
    REDIS_KEY_CHAT_REVOKED,
    REDIS_KEY_CHAT_STREAM,
    REDIS_KEY_CHAT_TASK,
)

from app.core.celery import celery_app
from app.core.config import get_settings
from app.db.session import get_celery_session
from app.models.db_models import Chat, Message, MessageStreamStatus, User
from app.services.claude_agent import ClaudeAgentService
from app.services.exceptions import ClaudeAgentException, UserException
from app.services.sandbox import SandboxService
from app.services.sandbox_providers import create_sandbox_provider
from app.services.streaming.events import StreamEvent
from app.services.user import UserService

logger = logging.getLogger(__name__)

settings = get_settings()

STREAM_MAX_LEN = 10_000


class StreamCancelled(Exception):
    def __init__(self, final_content: str) -> None:
        super().__init__("Stream cancelled")
        self.final_content = final_content


@dataclass
class StreamOutcome:
    events: list[StreamEvent]
    final_content: str
    total_cost: float


class SessionUpdateCallback:
    def __init__(
        self,
        chat_id: str,
        assistant_message_id: str | None,
        session_factory: Any,
        session_container: dict[str, Any],
    ) -> None:
        self.chat_id = chat_id
        self.assistant_message_id = assistant_message_id
        self.session_factory = session_factory
        self.session_container = session_container

    def __call__(self, new_session_id: str) -> None:
        self.session_container["session_id"] = new_session_id
        asyncio.create_task(
            _update_session_id(
                self.chat_id,
                self.assistant_message_id,
                new_session_id,
                self.session_factory,
            )
        )


@dataclass
class StreamContext:
    chat_id: str
    stream: AsyncIterator[StreamEvent]
    task: Any
    redis_client: "Redis[str] | None"
    ai_service: ClaudeAgentService
    assistant_message_id: str | None
    sandbox_service: SandboxService | None
    chat: Chat
    session_factory: Any
    events: list[StreamEvent]
    was_cancelled: bool = False
    cancel_requested: bool = False


def _hydrate_user_and_chat(
    user_data: dict[str, Any], chat_data: dict[str, Any]
) -> tuple[User, Chat]:
    user = User(
        id=uuid.UUID(user_data["id"]),
        email=user_data["email"],
        username=user_data["username"],
    )

    chat = Chat(
        id=uuid.UUID(chat_data["id"]),
        user_id=uuid.UUID(chat_data["user_id"]),
        title=chat_data["title"],
        sandbox_id=chat_data.get("sandbox_id"),
        session_id=chat_data.get("session_id"),
        sandbox_provider=chat_data.get("sandbox_provider"),
    )
    return user, chat


async def _publish_stream_entry(
    redis: "Redis[str] | None",
    chat_id: str,
    kind: str,
    payload: dict[str, Any] | str | None = None,
) -> None:
    if not redis:
        return

    fields: dict[str, str | int | float] = {"kind": kind}
    if payload is not None:
        if isinstance(payload, str):
            fields["payload"] = payload
        else:
            fields["payload"] = json.dumps(payload, ensure_ascii=False)

    try:
        # XADD appends to Redis stream (append-only log). maxlen with approximate=True
        # caps stream size for memory efficiency, allowing slight overage for performance.
        await redis.xadd(
            REDIS_KEY_CHAT_STREAM.format(chat_id=chat_id),
            fields,
            maxlen=STREAM_MAX_LEN,
            approximate=True,
        )
    except Exception as exc:
        logger.warning("Failed to append stream entry for chat %s: %s", chat_id, exc)


async def _update_message_status(
    assistant_message_id: str,
    stream_status: MessageStreamStatus,
) -> None:
    if not assistant_message_id:
        return

    async with get_celery_session() as (session_factory, engine):
        try:
            async with session_factory() as db:
                message_uuid = uuid.UUID(assistant_message_id)
                query = select(Message).filter(Message.id == message_uuid)
                result = await db.execute(query)
                message = result.scalar_one_or_none()

                if message:
                    message.stream_status = stream_status
                    db.add(message)
                    await db.commit()
        except Exception as exc:
            logger.error("Failed to update message status: %s", exc)


async def _check_task_revocation(chat_id: str, redis_client: "Redis[str]") -> bool:
    try:
        revoked = await redis_client.get(REDIS_KEY_CHAT_REVOKED.format(chat_id=chat_id))
        return revoked in ("1", b"1")
    except Exception as exc:
        logger.error("Failed to check revocation status: %s", exc)
        return False


async def _wait_for_task_revocation(chat_id: str, redis_client: "Redis[str]") -> None:
    while True:
        if await _check_task_revocation(chat_id, redis_client):
            return

        await asyncio.sleep(settings.REVOCATION_POLL_INTERVAL_SECONDS)


async def _cancel_stream_safely(ctx: StreamContext) -> None:
    if not ctx.cancel_requested:
        ctx.cancel_requested = True
        try:
            await ctx.ai_service.cancel_active_stream()
        except Exception as exc:
            logger.error("Failed to cancel active stream: %s", exc)


async def _monitor_revocation(
    ctx: StreamContext, main_task: asyncio.Task[None] | None
) -> None:
    # Runs concurrently with stream processing to detect user-initiated cancellation.
    # When a revocation is detected: (1) cancel the AI stream to stop generating,
    # (2) cancel the main processing task to unblock any awaits. Both cancellations
    # are needed because the stream might be blocked waiting for data, and we need
    # the main task's CancelledError to break out of the iteration loop cleanly.
    if not ctx.redis_client:
        return

    try:
        await _wait_for_task_revocation(ctx.chat_id, ctx.redis_client)
    except asyncio.CancelledError:
        raise

    ctx.was_cancelled = True
    await _cancel_stream_safely(ctx)

    if main_task:
        main_task.cancel()


async def _cleanup_task_resources(
    chat_id: str,
    redis_client: "Redis[str] | None" = None,
) -> None:
    if redis_client:
        try:
            await redis_client.delete(REDIS_KEY_CHAT_TASK.format(chat_id=chat_id))
            await redis_client.delete(REDIS_KEY_CHAT_REVOKED.format(chat_id=chat_id))
        except Exception as exc:
            logger.error("Failed to cleanup Redis keys: %s", exc)

        try:
            await redis_client.close()
        except Exception as e:
            logger.debug("Error closing Redis client: %s", e)


async def _save_message_content(
    assistant_message_id: str,
    events: list[StreamEvent],
    total_cost_usd: float,
    stream_status: MessageStreamStatus,
) -> None:
    if not assistant_message_id or not events:
        return

    async with get_celery_session() as (session_factory, engine):
        try:
            async with session_factory() as db:
                message_uuid = uuid.UUID(assistant_message_id)
                query = select(Message).filter(Message.id == message_uuid)
                result = await db.execute(query)
                message = result.scalar_one_or_none()

                if message:
                    message.content = json.dumps(events, ensure_ascii=False)
                    message.total_cost_usd = total_cost_usd
                    message.stream_status = stream_status
                    db.add(message)
                    await db.commit()
        except Exception as exc:
            logger.error("Failed to save message content: %s", exc)


async def _update_session_id(
    chat_id: str,
    assistant_message_id: str | None,
    session_id: str,
    session_factory: Any = None,
) -> None:
    if not session_factory:
        return

    try:
        async with session_factory() as db:
            chat_uuid = uuid.UUID(chat_id)
            chat_query = select(Chat).filter(Chat.id == chat_uuid)
            chat_result = await db.execute(chat_query)
            chat_record = chat_result.scalar_one_or_none()
            if chat_record:
                chat_record.session_id = session_id
                db.add(chat_record)

            if assistant_message_id:
                message_uuid = uuid.UUID(assistant_message_id)
                message_query = select(Message).filter(Message.id == message_uuid)
                message_result = await db.execute(message_query)
                message = message_result.scalar_one_or_none()
                if message:
                    message.session_id = session_id
                    db.add(message)

            await db.commit()
    except Exception as exc:
        logger.error("Failed to update session_id: %s", exc)


async def _prepare_stream(chat_id: str, task: Any) -> "Redis[str] | None":
    try:
        redis_client: "Redis[str]" = Redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
    except Exception as exc:
        logger.error("Failed to connect to Redis: %s", exc)
        return None

    try:
        await redis_client.delete(REDIS_KEY_CHAT_STREAM.format(chat_id=chat_id))
        await redis_client.setex(
            REDIS_KEY_CHAT_TASK.format(chat_id=chat_id),
            settings.TASK_TTL_SECONDS,
            task.request.id,
        )
    except Exception as exc:
        logger.warning("Failed to initialize stream for chat %s: %s", chat_id, exc)
    return redis_client


async def _create_checkpoint_if_needed(
    sandbox_service: SandboxService | None,
    chat: Chat,
    assistant_message_id: str | None,
    session_factory: Any,
) -> None:
    if not (sandbox_service and chat.sandbox_id and assistant_message_id):
        return

    try:
        checkpoint_id = await sandbox_service.create_checkpoint(
            chat.sandbox_id, assistant_message_id
        )
        if not checkpoint_id:
            return

        async with session_factory() as db:
            message_uuid = uuid.UUID(assistant_message_id)
            query = select(Message).filter(Message.id == message_uuid)
            result = await db.execute(query)
            message = result.scalar_one_or_none()
            if message:
                message.checkpoint_id = checkpoint_id
                db.add(message)
                await db.commit()
    except Exception as exc:
        logger.warning("Failed to create checkpoint: %s", exc)


async def _process_stream_events(ctx: StreamContext) -> None:
    # Dual-task pattern: processes stream events while monitoring for user cancellation.
    # The revocation_task polls Redis for a cancellation flag. If set, it triggers
    # CancelledError on the main task, which is caught below to perform graceful cleanup.
    # This allows immediate response to user cancellation without waiting for the next event.
    stream_iter = ctx.stream.__aiter__()
    revocation_task: asyncio.Task[None] | None = None
    current_task = asyncio.current_task()

    if ctx.redis_client:
        revocation_task = asyncio.create_task(_monitor_revocation(ctx, current_task))

    try:
        while True:
            try:
                event = await stream_iter.__anext__()
            except StopAsyncIteration:
                break
            except asyncio.CancelledError:
                if ctx.was_cancelled:
                    await _cancel_stream_safely(ctx)
                    break
                raise

            ctx.events.append(deepcopy(event))
            await _publish_stream_entry(
                ctx.redis_client, ctx.chat_id, "content", {"event": event}
            )

            ctx.task.update_state(
                state="PROGRESS",
                meta={"status": "Processing", "events_emitted": len(ctx.events)},
            )
    finally:
        if revocation_task:
            revocation_task.cancel()
            with suppress(asyncio.CancelledError):
                await revocation_task


async def _finalize_stream(
    ctx: StreamContext, status: MessageStreamStatus
) -> StreamOutcome:
    total_cost = ctx.ai_service.get_total_cost_usd()
    final_content = json.dumps(ctx.events, ensure_ascii=False)

    await _publish_stream_entry(ctx.redis_client, ctx.chat_id, "complete")

    if ctx.assistant_message_id and ctx.events:
        await _save_message_content(
            ctx.assistant_message_id,
            ctx.events,
            total_cost,
            status,
        )

    if status == MessageStreamStatus.COMPLETED:
        await _create_checkpoint_if_needed(
            ctx.sandbox_service, ctx.chat, ctx.assistant_message_id, ctx.session_factory
        )

    return StreamOutcome(
        events=ctx.events,
        final_content=final_content,
        total_cost=total_cost,
    )


async def _drain_ai_stream(
    *,
    chat_id: str,
    stream: Any,
    task: Any,
    redis_client: "Redis[str] | None",
    ai_service: ClaudeAgentService,
    events: list[StreamEvent],
    assistant_message_id: str | None,
    sandbox_service: SandboxService | None,
    chat: Chat,
    session_factory: Any,
) -> StreamOutcome:
    ctx = StreamContext(
        chat_id=chat_id,
        stream=stream,
        task=task,
        redis_client=redis_client,
        ai_service=ai_service,
        assistant_message_id=assistant_message_id,
        sandbox_service=sandbox_service,
        chat=chat,
        session_factory=session_factory,
        events=events,
    )

    try:
        await _process_stream_events(ctx)

        if ctx.was_cancelled:
            if not ctx.cancel_requested:
                await ai_service.cancel_active_stream()
            await _update_message_status(
                assistant_message_id or "", MessageStreamStatus.INTERRUPTED
            )
            outcome = await _finalize_stream(ctx, MessageStreamStatus.INTERRUPTED)
            raise StreamCancelled(outcome.final_content)

        if not ctx.events:
            raise ClaudeAgentException("Stream completed without any events")

        return await _finalize_stream(ctx, MessageStreamStatus.COMPLETED)

    except StreamCancelled:
        raise
    except Exception as exc:
        logger.error("Error in stream processing: %s", exc)

        await _publish_stream_entry(redis_client, chat_id, "error", {"error": str(exc)})
        await _update_message_status(
            assistant_message_id or "", MessageStreamStatus.FAILED
        )

        if assistant_message_id and events:
            await _save_message_content(
                assistant_message_id,
                events,
                ai_service.get_total_cost_usd(),
                MessageStreamStatus.FAILED,
            )

        raise


async def process_chat_stream(  # type: ignore[return]
    task: Any,
    prompt: str,
    system_prompt: str,
    custom_instructions: str | None,
    user_data: dict[str, Any],
    chat_data: dict[str, Any],
    model_id: str,
    sandbox_service: SandboxService,
    permission_mode: str = "auto",
    session_id: str | None = None,
    assistant_message_id: str | None = None,
    thinking_mode: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    user, chat = _hydrate_user_and_chat(user_data, chat_data)

    chat_id = str(chat.id)
    session_container: dict[str, Any] = {"session_id": session_id}
    events: list[StreamEvent] = []

    redis_client = await _prepare_stream(chat_id, task)
    task.update_state(state="PROGRESS", meta={"status": "Starting AI processing"})

    try:
        async with get_celery_session() as (TaskSessionLocal, task_engine):
            async with ClaudeAgentService(
                session_factory=TaskSessionLocal
            ) as ai_service:
                session_callback = SessionUpdateCallback(
                    chat_id=chat_id,
                    assistant_message_id=assistant_message_id,
                    session_factory=TaskSessionLocal,
                    session_container=session_container,
                )

                stream = ai_service.get_ai_stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    custom_instructions=custom_instructions,
                    user=user,
                    chat=chat,
                    permission_mode=permission_mode,
                    model_id=model_id,
                    session_id=session_id,
                    session_callback=session_callback,
                    thinking_mode=thinking_mode,
                    attachments=attachments,
                )

                try:
                    outcome = await _drain_ai_stream(
                        chat_id=chat_id,
                        stream=stream,
                        task=task,
                        redis_client=redis_client,
                        ai_service=ai_service,
                        events=events,
                        assistant_message_id=assistant_message_id,
                        sandbox_service=sandbox_service,
                        chat=chat,
                        session_factory=TaskSessionLocal,
                    )
                except StreamCancelled as cancelled:
                    raise Ignore() from cancelled

                task.update_state(
                    state="SUCCESS",
                    meta={
                        "status": "Completed",
                        "content": outcome.final_content,
                        "session_id": session_container["session_id"],
                    },
                )

                return outcome.final_content

    finally:
        await _cleanup_task_resources(chat_id, redis_client)


async def _initialize_and_process_chat(
    task: Any,
    prompt: str,
    system_prompt: str,
    custom_instructions: str | None,
    user_data: dict[str, Any],
    chat_data: dict[str, Any],
    model_id: str,
    permission_mode: str,
    session_id: str | None,
    assistant_message_id: str | None,
    thinking_mode: str | None,
    attachments: list[dict[str, Any]] | None,
) -> str:
    async with get_celery_session() as (SessionFactory, engine):
        async with SessionFactory() as db:
            user_id = uuid.UUID(user_data["id"])

            user_service = UserService(session_factory=SessionFactory)

            try:
                user_settings = await user_service.get_user_settings(user_id, db=db)
            except UserException:
                raise UserException("User settings not found")

            provider_type = (
                chat_data.get("sandbox_provider") or user_settings.sandbox_provider
            )
            provider = create_sandbox_provider(
                provider_type=provider_type,
                api_key=user_settings.e2b_api_key,
            )

        sandbox_service = SandboxService(
            provider=provider, session_factory=SessionFactory
        )
        try:
            return await process_chat_stream(
                task,
                prompt=prompt,
                system_prompt=system_prompt,
                custom_instructions=custom_instructions,
                user_data=user_data,
                chat_data=chat_data,
                model_id=model_id,
                permission_mode=permission_mode,
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                thinking_mode=thinking_mode,
                attachments=attachments,
                sandbox_service=sandbox_service,
            )
        finally:
            await sandbox_service.cleanup()


@celery_app.task(bind=True)
def process_chat(
    self: Any,
    prompt: str,
    system_prompt: str,
    custom_instructions: str | None,
    user_data: dict[str, Any],
    chat_data: dict[str, Any],
    model_id: str,
    permission_mode: str = "auto",
    session_id: str | None = None,
    assistant_message_id: str | None = None,
    thinking_mode: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(
            _initialize_and_process_chat(
                task=self,
                prompt=prompt,
                system_prompt=system_prompt,
                custom_instructions=custom_instructions,
                user_data=user_data,
                chat_data=chat_data,
                model_id=model_id,
                permission_mode=permission_mode,
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                thinking_mode=thinking_mode,
                attachments=attachments,
            )
        )
    finally:
        loop.close()
