import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.celery import celery_app
from app.core.config import get_settings
from app.db.session import get_celery_session
from app.models.db_models import (
    Chat,
    Message,
    MessageRole,
    MessageStreamStatus,
    ScheduledTask,
    TaskExecution,
    TaskExecutionStatus,
    TaskStatus,
    User,
)
from app.prompts.system_prompt import build_system_prompt_for_chat
from app.services.refresh_token import RefreshTokenService
from app.services.sandbox import SandboxService
from app.services.sandbox_providers import (
    DockerConfig,
    SandboxProviderType,
    create_sandbox_provider,
)
from app.services.scheduler import (
    calculate_next_execution,
    check_duplicate_execution,
    complete_task_execution,
    load_task_and_user,
    update_task_after_execution,
)
from app.services.user import UserService
from app.tasks.chat_processor import process_chat_stream
from app.utils.validators import (
    APIKeyValidationError,
    validate_e2b_api_key,
    validate_model_api_keys,
)

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="check_scheduled_tasks")
def check_scheduled_tasks() -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_check_scheduled_tasks())
    finally:
        loop.close()


async def _check_scheduled_tasks() -> dict[str, Any]:
    async with get_celery_session() as (session_factory, engine):
        try:
            async with session_factory() as db:
                now = datetime.now(timezone.utc)

                query = (
                    select(ScheduledTask)
                    .where(
                        ScheduledTask.enabled,
                        ScheduledTask.status == TaskStatus.ACTIVE,
                        ScheduledTask.next_execution <= now,
                        ScheduledTask.next_execution.isnot(None),
                    )
                    .order_by(ScheduledTask.next_execution)
                    .limit(100)
                )

                result = await db.execute(query)
                tasks = result.scalars().all()

                for task in tasks:
                    next_exec = calculate_next_execution(task, from_time=now)

                    if next_exec is None:
                        task.next_execution = None
                        task.status = TaskStatus.PENDING
                    else:
                        task.next_execution = next_exec

                    db.add(task)

                await db.commit()

                for task in tasks:
                    execute_scheduled_task.delay(str(task.id))

                return {"tasks_triggered": len(tasks)}

        except Exception as e:
            logger.error("Error checking scheduled tasks: %s", e)
            return {"error": str(e)}


@celery_app.task(bind=True, name="execute_scheduled_task")
def execute_scheduled_task(self: Any, task_id: str) -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_execute_scheduled_task(self, task_id))
    finally:
        loop.close()


async def _create_task_chat_and_messages(
    db: Any, scheduled_task: ScheduledTask, user: User, sandbox_id: str
) -> tuple[Chat, Message, Message]:
    chat = Chat(
        title=scheduled_task.task_name,
        user_id=user.id,
        sandbox_id=sandbox_id,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)

    user_message = Message(
        chat_id=chat.id,
        content=scheduled_task.prompt_message,
        role=MessageRole.USER,
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    assistant_message = Message(
        chat_id=chat.id,
        content="",
        role=MessageRole.ASSISTANT,
        model_id=scheduled_task.model_id,
        stream_status=MessageStreamStatus.IN_PROGRESS,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    return chat, user_message, assistant_message


async def _validate_user_api_keys(
    db: Any,
    user: User,
    scheduled_task: ScheduledTask,
    task_uuid: uuid.UUID,
    start_time: datetime,
    model_id: str,
    session_factory: Any = None,
) -> tuple[Any, dict[str, Any] | None]:
    user_service = UserService()

    try:
        user_settings = await user_service.get_user_settings(user.id, db=db)
        if user_settings.sandbox_provider == "e2b":
            validate_e2b_api_key(user_settings)
        await validate_model_api_keys(user_settings, model_id, session_factory)
        return user_settings, None
    except (ValueError, APIKeyValidationError) as e:
        logger.error("API keys not configured for user %s: %s", user.id, e)
        execution = TaskExecution(
            task_id=scheduled_task.id,
            executed_at=start_time,
            completed_at=datetime.now(timezone.utc),
            status=TaskExecutionStatus.FAILED,
            error_message=str(e),
        )
        db.add(execution)
        await update_task_after_execution(
            db, task_uuid, start_time, success=False, error_message=str(e)
        )
        await db.commit()
        return None, {"error": str(e)}


async def _create_and_initialize_sandbox(
    user_settings: Any, user: User, session_factory: Any = None
) -> tuple[SandboxService, str]:
    provider_type = SandboxProviderType(user_settings.sandbox_provider)

    docker_config = None
    if provider_type == SandboxProviderType.DOCKER:
        docker_config = DockerConfig(
            image=settings.DOCKER_IMAGE,
            network=settings.DOCKER_NETWORK,
            host=settings.DOCKER_HOST,
            preview_base_url=settings.DOCKER_PREVIEW_BASE_URL,
        )

    provider = create_sandbox_provider(
        provider_type=provider_type,
        api_key=user_settings.e2b_api_key,
        docker_config=docker_config,
    )

    sandbox_service = SandboxService(provider, session_factory=session_factory)
    sandbox_id = await sandbox_service.create_sandbox()

    await sandbox_service.initialize_sandbox(
        sandbox_id=sandbox_id,
        github_token=user_settings.github_personal_access_token,
        openrouter_api_key=user_settings.openrouter_api_key,
        custom_env_vars=user_settings.custom_env_vars,
        custom_skills=user_settings.custom_skills,
        custom_slash_commands=user_settings.custom_slash_commands,
        custom_agents=user_settings.custom_agents,
        user_id=str(user.id),
        auto_compact_disabled=user_settings.auto_compact_disabled,
    )

    return sandbox_service, sandbox_id


async def _setup_execution_chat_context(
    session_factory: Any,
    scheduled_task: ScheduledTask,
    user: User,
    sandbox_id: str,
    execution_id: uuid.UUID,
) -> tuple[Chat, Message, Message]:
    async with session_factory() as db:
        chat, user_message, assistant_message = await _create_task_chat_and_messages(
            db, scheduled_task, user, sandbox_id
        )
        chat_id = chat.id
        message_id = user_message.id

    async with session_factory() as db:
        exec_query = select(TaskExecution).where(TaskExecution.id == execution_id)
        exec_result = await db.execute(exec_query)
        execution = exec_result.scalar_one_or_none()
        if execution:
            execution.chat_id = chat_id
            execution.message_id = message_id
            db.add(execution)
            await db.commit()

    return chat, user_message, assistant_message


async def _execute_task_in_sandbox(
    task: Any,
    scheduled_task: ScheduledTask,
    user: User,
    chat: Chat,
    assistant_message: Message,
    user_settings: Any,
    model_id: str,
    sandbox_service: SandboxService,
) -> None:
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
    }

    chat_data = {
        "id": str(chat.id),
        "user_id": str(user.id),
        "title": chat.title,
        "sandbox_id": chat.sandbox_id,
        "session_id": None,
    }

    system_prompt = build_system_prompt_for_chat(chat.sandbox_id, user_settings)
    custom_instructions = user_settings.custom_instructions

    await process_chat_stream(
        task,
        prompt=scheduled_task.prompt_message,
        system_prompt=system_prompt,
        custom_instructions=custom_instructions,
        user_data=user_data,
        chat_data=chat_data,
        model_id=model_id,
        sandbox_service=sandbox_service,
        permission_mode="auto",
        session_id=None,
        assistant_message_id=str(assistant_message.id),
        thinking_mode="ultra",
        attachments=None,
    )


async def _execute_scheduled_task(task: Any, task_id: str) -> dict[str, Any]:
    async with get_celery_session() as (session_factory, engine):
        start_time = datetime.now(timezone.utc)
        execution_id: uuid.UUID | None = None
        sandbox_service: SandboxService | None = None
        task_uuid: uuid.UUID | None = None

        try:
            async with session_factory() as db:
                task_uuid = uuid.UUID(task_id)

                if await check_duplicate_execution(db, task_uuid, start_time):
                    return {"status": "skipped", "reason": "already_executing"}

                scheduled_task, user = await load_task_and_user(db, task_uuid)

                if not scheduled_task:
                    logger.error("Scheduled task %s not found", task_id)
                    return {"error": "Task not found"}

                if not user:
                    logger.error(
                        "User %s not found for task %s", scheduled_task.user_id, task_id
                    )
                    return {"error": "User not found"}

                if not scheduled_task.enabled:
                    return {"status": "skipped", "reason": "disabled"}

                model_id = scheduled_task.model_id or "claude-sonnet-4-5"

                user_settings, error = await _validate_user_api_keys(
                    db,
                    user,
                    scheduled_task,
                    task_uuid,
                    start_time,
                    model_id,
                    session_factory,
                )
                if error:
                    return error

                execution = TaskExecution(
                    task_id=scheduled_task.id,
                    executed_at=start_time,
                    status=TaskExecutionStatus.RUNNING,
                )
                db.add(execution)
                await db.commit()
                await db.refresh(execution)
                execution_id = execution.id

            sandbox_service, sandbox_id = await _create_and_initialize_sandbox(
                user_settings, user, session_factory
            )

            try:
                (
                    chat,
                    user_message,
                    assistant_message,
                ) = await _setup_execution_chat_context(
                    session_factory, scheduled_task, user, sandbox_id, execution_id
                )

                try:
                    await _execute_task_in_sandbox(
                        task,
                        scheduled_task,
                        user,
                        chat,
                        assistant_message,
                        user_settings,
                        model_id,
                        sandbox_service,
                    )

                    async with session_factory() as db:
                        await complete_task_execution(
                            db, execution_id, TaskExecutionStatus.SUCCESS
                        )
                        await update_task_after_execution(
                            db, task_uuid, start_time, success=True
                        )
                        await db.commit()

                    return {
                        "status": "success",
                        "task_id": task_id,
                        "chat_id": str(chat.id),
                        "execution_id": str(execution_id),
                    }

                except Exception as e:
                    logger.error("Error executing scheduled task %s: %s", task_id, e)

                    async with session_factory() as db:
                        if execution_id:
                            await complete_task_execution(
                                db,
                                execution_id,
                                TaskExecutionStatus.FAILED,
                                error_message=str(e),
                            )
                        await update_task_after_execution(
                            db,
                            task_uuid,
                            start_time,
                            success=False,
                            error_message=str(e),
                        )
                        await db.commit()

                    return {"error": str(e)}

            finally:
                await sandbox_service.delete_sandbox(sandbox_id)
                await sandbox_service.cleanup()

        except Exception as e:
            logger.error("Fatal error in execute_scheduled_task: %s", e)
            return {"error": str(e)}


@celery_app.task(name="cleanup_expired_refresh_tokens")
def cleanup_expired_refresh_tokens() -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_cleanup_expired_refresh_tokens())
    finally:
        loop.close()


async def _cleanup_expired_refresh_tokens() -> dict[str, Any]:
    async with get_celery_session() as (session_factory, engine):
        try:
            refresh_token_service = RefreshTokenService(session_factory=session_factory)
            deleted_count = await refresh_token_service.cleanup_expired_tokens()
            logger.info("Cleaned up %s expired refresh tokens", deleted_count)
            return {"deleted_count": deleted_count}
        except Exception as e:
            logger.error("Error cleaning up expired refresh tokens: %s", e)
            return {"error": str(e)}
