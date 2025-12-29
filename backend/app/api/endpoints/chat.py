import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

from celery.exceptions import NotRegistered
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sse_starlette.sse import EventSourceResponse

from app.constants import (
    REDIS_KEY_CHAT_CANCEL,
    REDIS_KEY_CHAT_REVOKED,
    REDIS_KEY_CHAT_STREAM,
    REDIS_KEY_CHAT_TASK,
    REDIS_KEY_PERMISSION_RESPONSE,
)
from app.core.celery import celery_app
from app.core.config import get_settings
from app.core.deps import get_chat_service
from app.core.security import get_current_user
from app.models.db_models import User, MessageStreamStatus
from app.models.schemas import (
    Chat as ChatSchema,
    ChatCompletionResponse,
    ChatCreate,
    ChatStatusResponse,
    ChatUpdate,
    ChatRequest,
    ContextUsage,
    EnhancePromptResponse,
    PaginatedChats,
    PaginatedMessages,
    PaginationParams,
    PermissionRespondResponse,
    RestoreRequest,
)
from app.services.chat import ChatService
from app.services.exceptions import ChatException, ClaudeAgentException
from app.services.permission_manager import PermissionManager
from app.utils.redis import redis_connection, redis_pubsub
from app.models.schemas.errors import HTTPErrorResponse

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

INACTIVE_TASK_RESPONSE = {
    "has_active_task": False,
    "last_event_id": None,
}


async def _ensure_chat_access(
    chat_id: UUID, chat_service: ChatService, current_user: User
) -> None:
    try:
        await chat_service.get_chat(chat_id, current_user)
    except ChatException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or access denied",
        )


async def _monitor_stream_cancellation(
    chat_id: UUID, cancel_event: asyncio.Event, redis: "Redis[str]"
) -> None:
    try:
        async with redis_pubsub(
            redis, REDIS_KEY_CHAT_CANCEL.format(chat_id=chat_id)
        ) as pubsub:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message.get("type") == "message":
                    logger.info("Stream cancellation received for chat %s", chat_id)
                    cancel_event.set()
                    break
    except asyncio.CancelledError:
        logger.debug("Cancellation monitor task cancelled for chat %s", chat_id)
        raise
    except Exception as e:
        logger.error(
            "Error monitoring cancellation for chat %s: %s", chat_id, e, exc_info=True
        )


async def _replay_stream_backlog(
    redis: "Redis[str]", stream_name: str, min_id: str
) -> AsyncIterator[dict[str, Any]]:
    # Replays missed events from Redis stream for SSE reconnection support.
    # When a client reconnects with Last-Event-ID, this fetches all events since that ID.
    # XRANGE returns entries between min and max IDs (inclusive). "+" means latest entry.
    try:
        backlog = await redis.xrange(stream_name, min=min_id, max="+")
    except Exception as e:
        logger.warning("Failed to replay stream backlog from %s: %s", stream_name, e)
        backlog = []

    for entry_id, fields in backlog:
        formatted = {
            "id": entry_id,
            "event": fields.get("kind", "content"),
            "data": fields.get("payload", "") or "",
        }
        yield formatted
        if formatted["event"] in {"complete", "error"}:
            return


async def _stream_live_redis_events(
    redis: "Redis[str]",
    stream_name: str,
    chat_id: UUID,
    last_id: str,
    cancel_event: asyncio.Event,
) -> AsyncIterator[dict[str, Any]]:
    # Polls Redis stream for new events using XREAD with 5s blocking timeout.
    # Checks cancellation flag before each poll to enable responsive stream termination.
    if (
        await redis.get(REDIS_KEY_CHAT_REVOKED.format(chat_id=chat_id))
        or cancel_event.is_set()
    ):
        logger.info("Stream already cancelled for chat %s", chat_id)
        yield {
            "event": "complete",
            "data": json.dumps({"status": "cancelled"}),
        }
        return

    while True:
        if cancel_event.is_set():
            logger.info("Stream cancelled for chat %s", chat_id)
            yield {
                "event": "complete",
                "data": json.dumps({"status": "cancelled"}),
            }
            return

        try:
            # XREAD blocks up to 1s waiting for new entries after last_id.
            # Returns immediately if new data arrives, or empty after timeout.
            response = await redis.xread(
                {stream_name: last_id},
                block=1000,
                count=10,
            )
        except Exception as e:
            logger.debug("Redis xread error, retrying: %s", e)
            await asyncio.sleep(0.5)
            continue

        if not response:
            continue

        _, messages = response[0]
        for entry_id, fields in messages:
            if entry_id == last_id:
                continue

            formatted = {
                "id": entry_id,
                "event": fields.get("kind", "content"),
                "data": fields.get("payload", "") or "",
            }
            yield formatted
            last_id = entry_id

            if formatted["event"] in {"complete", "error"}:
                return


async def _create_event_stream(
    chat_id: UUID, last_event_id: str | None
) -> AsyncIterator[dict[str, Any]]:
    # Two-phase SSE streaming: first replays any missed events (backlog), then switches
    # to live polling. A concurrent monitor task watches for cancellation requests.
    try:
        async with redis_connection() as redis:
            stream_name = REDIS_KEY_CHAT_STREAM.format(chat_id=chat_id)
            min_id = f"({last_event_id})" if last_event_id else "-"
            last_id = last_event_id

            async for item in _replay_stream_backlog(redis, stream_name, min_id):
                yield item
                last_id = item["id"]
                if item.get("event") in {"complete", "error"}:
                    return

            if not last_id:
                last_id = "0-0"

            cancel_event = asyncio.Event()
            monitor_task = asyncio.create_task(
                _monitor_stream_cancellation(chat_id, cancel_event, redis)
            )

            try:
                async for event in _stream_live_redis_events(
                    redis, stream_name, chat_id, last_id, cancel_event
                ):
                    yield event
                    if event.get("event") in {"complete", "error"}:
                        return
            finally:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

    except Exception as exc:
        logger.error(
            "Error in event stream for chat %s: %s", chat_id, exc, exc_info=True
        )
        yield {
            "event": "error",
            "data": json.dumps({"error": str(exc)}),
        }


@router.post(
    "/chats",
    response_model=ChatSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": HTTPErrorResponse, "description": "Bad request"},
        401: {"model": HTTPErrorResponse, "description": "Unauthorized"},
        429: {
            "model": HTTPErrorResponse,
            "description": "Daily message limit exceeded",
        },
        500: {"model": HTTPErrorResponse, "description": "Internal server error"},
        503: {"model": HTTPErrorResponse, "description": "Service unavailable"},
    },
)
async def create_chat(
    chat_data: ChatCreate,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatSchema:
    try:
        chat = await chat_service.create_chat(current_user, chat_data)
        return chat
    except ChatException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except SQLAlchemyError as e:
        logger.error("Database error creating chat: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating chat",
        )
    except RedisError as e:
        logger.error("Redis error creating chat: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )


@router.post("/chat", response_model=ChatCompletionResponse)
async def send_message(
    prompt: str = Form(...),
    chat_id: str = Form(...),
    model_id: str = Form(...),
    permission_mode: Literal["plan", "ask", "auto"] = Form("auto"),
    thinking_mode: str | None = Form(None),
    selected_prompt_name: str | None = Form(None),
    attached_files: list[UploadFile] = [],
    chat_service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        result = await chat_service.initiate_chat_completion(
            ChatRequest(
                prompt=prompt,
                chat_id=UUID(chat_id),
                model_id=model_id,
                attached_files=attached_files,
                permission_mode=permission_mode,
                thinking_mode=thinking_mode,
                selected_prompt_name=selected_prompt_name,
            ),
            current_user,
        )

        return {
            "chat_id": result["chat_id"],
            "message_id": result["message_id"],
        }
    except ChatException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/enhance-prompt", response_model=EnhancePromptResponse)
async def enhance_prompt(
    prompt: str = Form(...),
    model_id: str = Form(...),
    chat_service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    try:
        enhanced_prompt = await chat_service.ai_service.enhance_prompt(
            prompt, model_id, current_user
        )
        return {"enhanced_prompt": enhanced_prompt}
    except ClaudeAgentException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Unexpected error enhancing prompt: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enhance prompt",
        )


@router.get("/chats", response_model=PaginatedChats)
async def get_chats(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> PaginatedChats:
    return await chat_service.get_user_chats(current_user, pagination)


@router.get(
    "/chats/{chat_id}",
    response_model=ChatSchema,
    responses={
        401: {"model": HTTPErrorResponse, "description": "Unauthorized"},
        404: {"model": HTTPErrorResponse, "description": "Chat not found"},
        500: {"model": HTTPErrorResponse, "description": "Internal server error"},
    },
)
async def get_chat_detail(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatSchema:
    try:
        chat = await chat_service.get_chat(chat_id, current_user)
        return chat
    except ChatException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except SQLAlchemyError as e:
        logger.error("Database error retrieving chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while retrieving chat",
        )


@router.get("/chats/{chat_id}/context-usage", response_model=ContextUsage)
async def get_chat_context_usage(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ContextUsage:
    chat = await chat_service.get_chat(chat_id, current_user)
    tokens_used = chat.context_token_usage or 0
    context_window = settings.CONTEXT_WINDOW_TOKENS
    percentage = 0.0
    if context_window > 0:
        percentage = min((tokens_used / context_window) * 100, 100.0)

    return ContextUsage(
        tokens_used=tokens_used,
        context_window=context_window,
        percentage=percentage,
    )


@router.patch("/chats/{chat_id}", response_model=ChatSchema)
async def update_chat(
    chat_id: UUID,
    chat_update: ChatUpdate,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatSchema:
    try:
        chat = await chat_service.update_chat(chat_id, chat_update, current_user)
        return chat
    except ChatException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except SQLAlchemyError as e:
        logger.error("Database error updating chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while updating chat",
        )


@router.delete("/chats/all", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_chats(
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    await chat_service.delete_all_chats(current_user)


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    await chat_service.delete_chat(chat_id, current_user)


@router.get("/chats/{chat_id}/messages", response_model=PaginatedMessages)
async def get_chat_messages(
    chat_id: UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> PaginatedMessages:
    return await chat_service.get_chat_messages(chat_id, current_user, pagination)


@router.post("/chats/{chat_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_chat(
    chat_id: UUID,
    request: RestoreRequest,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    try:
        await chat_service.restore_to_checkpoint(
            chat_id, request.message_id, current_user
        )
    except ChatException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except SQLAlchemyError as e:
        logger.error("Database error restoring chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while restoring chat",
        )


@router.get("/chats/{chat_id}/stream")
async def stream_events(
    chat_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> EventSourceResponse:
    await _ensure_chat_access(chat_id, chat_service, current_user)

    last_event_id = request.headers.get("Last-Event-ID") or request.query_params.get(
        "lastEventId"
    )

    return EventSourceResponse(
        _create_event_stream(chat_id, last_event_id),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chats/{chat_id}/status", response_model=ChatStatusResponse)
async def get_stream_status(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> dict[str, Any]:
    await _ensure_chat_access(chat_id, chat_service, current_user)

    try:
        latest_assistant_message = (
            await chat_service.message_service.get_latest_assistant_message(chat_id)
        )

        task_key = REDIS_KEY_CHAT_TASK.format(chat_id=chat_id)
        revoked_key = REDIS_KEY_CHAT_REVOKED.format(chat_id=chat_id)
        stream_key = REDIS_KEY_CHAT_STREAM.format(chat_id=chat_id)

        if latest_assistant_message:
            if latest_assistant_message.stream_status in [
                MessageStreamStatus.COMPLETED,
                MessageStreamStatus.FAILED,
                MessageStreamStatus.INTERRUPTED,
            ]:
                async with redis_connection() as redis:
                    await redis.delete(task_key)
                return INACTIVE_TASK_RESPONSE.copy()

        async with redis_connection() as redis:
            task_id = await redis.get(task_key)

            if not task_id:
                return INACTIVE_TASK_RESPONSE.copy()

            revoked = await redis.get(revoked_key)
            if revoked:
                await redis.delete(task_key)
                return INACTIVE_TASK_RESPONSE.copy()

            try:
                task_result = celery_app.AsyncResult(task_id)
                task_state = task_result.state
            except NotRegistered:
                await redis.delete(task_key)
                return INACTIVE_TASK_RESPONSE.copy()

            is_active = task_state in ["PENDING", "STARTED", "PROGRESS"]

            if not is_active:
                await redis.delete(task_key)
                return INACTIVE_TASK_RESPONSE.copy()

            try:
                # XREVRANGE reads stream in reverse (newest first). count=1 gets the latest entry.
                latest_entry = await redis.xrevrange(stream_key, count=1)
                last_event_id = latest_entry[0][0] if latest_entry else None
            except RedisError:
                last_event_id = None

            return {
                "has_active_task": True,
                "message_id": latest_assistant_message.id
                if latest_assistant_message
                else None,
                "last_event_id": last_event_id,
            }
    except RedisError as e:
        logger.error(
            "Redis error checking chat status %s: %s", chat_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )
    except SQLAlchemyError as e:
        logger.error(
            "Database error checking chat status %s: %s", chat_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check chat status",
        )


@router.delete("/chats/{chat_id}/stream", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_stream(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    await _ensure_chat_access(chat_id, chat_service, current_user)

    try:
        async with redis_connection() as redis:
            task_key = REDIS_KEY_CHAT_TASK.format(chat_id=chat_id)
            task_id = await redis.get(task_key)

            if not task_id:
                return

            try:
                await redis.setex(
                    REDIS_KEY_CHAT_REVOKED.format(chat_id=chat_id),
                    settings.CHAT_REVOKED_KEY_TTL_SECONDS,
                    "1",
                )
                await redis.publish(
                    REDIS_KEY_CHAT_CANCEL.format(chat_id=chat_id), "cancel"
                )
            except RedisError as e:
                logger.error(
                    "Failed to stop chat stream %s: %s", chat_id, e, exc_info=True
                )

    except RedisError as e:
        logger.error(
            "Redis error stopping chat stream %s: %s", chat_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )


@router.post(
    "/chats/{chat_id}/permissions/{request_id}/respond",
    response_model=PermissionRespondResponse,
    status_code=status.HTTP_200_OK,
)
async def respond_to_permission(
    chat_id: UUID,
    request_id: str,
    approved: bool = Form(...),
    alternative_instruction: str | None = Form(None),
    user_answers: str | None = Form(None, max_length=50000),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> PermissionRespondResponse:
    await _ensure_chat_access(chat_id, chat_service, current_user)

    parsed_answers = None
    if user_answers:
        try:
            parsed_answers = json.loads(user_answers)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in user_answers: %s", e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON format for user_answers",
            )
        if not isinstance(parsed_answers, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_answers must be a JSON object",
            )

    try:
        async with redis_connection() as redis:
            permission_manager = PermissionManager(redis)
            success = await permission_manager.respond_to_permission(
                request_id, approved, alternative_instruction, parsed_answers
            )

            if not success:
                # When a permission request is not found (expired or never existed), we publish
                # a "denied" message to the Redis pub/sub channel. This is necessary because
                # E2B's permission_server may still be blocked waiting on get_permission_response,
                # which subscribes to this channel. Without this publish, E2B would continue
                # waiting until its timeout (~5 min), leaving the tool stuck in "Waiting for
                # user response" state. By publishing the denied message, we wake up E2B's
                # waiting call immediately, allowing it to fail the tool right away.
                try:
                    expired_response = json.dumps(
                        {
                            "approved": False,
                            "alternative_instruction": "Permission request expired. Please try again.",
                        }
                    )
                    channel = REDIS_KEY_PERMISSION_RESPONSE.format(
                        request_id=request_id
                    )
                    await redis.publish(channel, expired_response)
                except Exception as e:
                    logger.warning("Failed to publish expired message: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Permission request not found or expired",
                )

            return PermissionRespondResponse(success=True)

    except HTTPException:
        raise
    except RedisError as e:
        logger.error(
            "Redis error responding to permission %s: %s", request_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )
