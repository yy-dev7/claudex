import logging
import uuid
from typing import Any, Callable

from e2b import AsyncSandbox
from e2b.sandbox.commands.command_handle import PtySize as E2BPtySize
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.constants import (
    SANDBOX_AUTO_PAUSE_TIMEOUT,
    SANDBOX_DEFAULT_COMMAND_TIMEOUT,
    SANDBOX_SYSTEM_VARIABLES,
)
from app.core.config import get_settings
from app.services.exceptions import ErrorCode, SandboxException
from app.services.sandbox_providers.base import LISTENING_PORTS_COMMAND, SandboxProvider
from app.services.sandbox_providers.types import (
    CommandResult,
    FileContent,
    PreviewLink,
    PtyDataCallbackType,
    PtySession,
    PtySize,
)

logger = logging.getLogger(__name__)

settings = get_settings()

SANDBOX_DEFAULT_TIMEOUT = 3600
EXCLUDED_PREVIEW_PORTS = {49982, 49983, 22, 4040, 3456, 8765}
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

E2B_SYSTEM_VARIABLES = SANDBOX_SYSTEM_VARIABLES + ["E2B_SANDBOX"]


def is_retryable_error(exception: BaseException) -> bool:
    error_message = str(exception)
    return not ("401" in error_message or "403" in error_message)


RETRY_CONFIG: dict[str, Any] = {
    "stop": stop_after_attempt(MAX_RETRIES),
    "wait": wait_exponential(multiplier=RETRY_BASE_DELAY, min=RETRY_BASE_DELAY, max=10),
    "retry": retry_if_exception(is_retryable_error),
    "before_sleep": before_sleep_log(logger, logging.WARNING),
    "reraise": True,
}


def normalize_e2b_pty_data(data: Any) -> bytes:
    if hasattr(data, "data"):
        return bytes(data.data)
    if isinstance(data, bytes):
        return data
    return str(data).encode("utf-8")


class E2BSandboxProvider(SandboxProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._active_sandboxes: dict[str, AsyncSandbox] = {}
        self._pty_sessions: dict[str, dict[str, Any]] = {}

    def _get_system_variables(self) -> list[str]:
        return E2B_SYSTEM_VARIABLES

    async def create_sandbox(self) -> str:
        try:
            sandbox = await self._retry_operation(
                AsyncSandbox.create,
                timeout=SANDBOX_DEFAULT_TIMEOUT,
                api_key=self.api_key,
                template=settings.E2B_TEMPLATE_ID,
                auto_pause=True,
            )
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                raise SandboxException(
                    error_msg,
                    error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                    status_code=429,
                )
            raise SandboxException(
                f"Failed to create sandbox: {error_msg}",
                error_code=ErrorCode.SANDBOX_CREATE_FAILED,
            )

        self._active_sandboxes[sandbox.sandbox_id] = sandbox
        return str(sandbox.sandbox_id)

    async def connect_sandbox(self, sandbox_id: str) -> bool:
        if sandbox_id in self._active_sandboxes:
            sandbox = self._active_sandboxes[sandbox_id]
            if await self._retry_operation(sandbox.is_running):
                return True
            del self._active_sandboxes[sandbox_id]

        sandbox = await self._retry_operation(
            AsyncSandbox.connect,
            sandbox_id=sandbox_id,
            api_key=self.api_key,
            auto_pause=True,
            timeout=SANDBOX_AUTO_PAUSE_TIMEOUT,
        )
        self._active_sandboxes[sandbox_id] = sandbox
        return True

    async def delete_sandbox(self, sandbox_id: str) -> None:
        if not sandbox_id:
            return

        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            try:
                sandbox = await AsyncSandbox.connect(
                    sandbox_id,
                    api_key=self.api_key,
                    auto_pause=True,
                )
            except Exception as e:
                logger.warning(
                    "Failed to connect to sandbox %s for cleanup: %s", sandbox_id, e
                )
                return

        if sandbox:
            await self._retry_operation(sandbox.kill)

        if sandbox_id in self._active_sandboxes:
            del self._active_sandboxes[sandbox_id]

        logger.info("Successfully deleted sandbox %s", sandbox_id)

    async def is_running(self, sandbox_id: str) -> bool:
        sandbox = self._active_sandboxes.get(sandbox_id)
        if not sandbox:
            return False
        return bool(await self._retry_operation(sandbox.is_running))

    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        background: bool = False,
        envs: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        sandbox = await self._get_sandbox(sandbox_id)
        effective_timeout = timeout or SANDBOX_DEFAULT_COMMAND_TIMEOUT
        env_map = envs or {}

        if background:
            process = await self._retry_operation(
                sandbox.commands.run,
                command,
                background=True,
                timeout=None,
                envs=env_map,
            )
            return CommandResult(
                stdout=f"Background process started (PID: {process.pid})",
                stderr="",
                exit_code=0,
            )

        result = await self._execute_with_timeout(
            self._retry_operation(
                sandbox.commands.run,
                command,
                timeout=effective_timeout,
                background=False,
                envs=env_map,
            ),
            effective_timeout,
            f"Command execution timed out after {effective_timeout}s",
        )

        return CommandResult(
            stdout=str(result.stdout),
            stderr=str(result.stderr),
            exit_code=result.exit_code,
        )

    async def write_file(
        self,
        sandbox_id: str,
        path: str,
        content: str | bytes,
    ) -> None:
        sandbox = await self._get_sandbox(sandbox_id)
        normalized_path = self.normalize_path(path)
        await self._retry_operation(sandbox.files.write, normalized_path, content)

    async def read_file(
        self,
        sandbox_id: str,
        path: str,
    ) -> FileContent:
        sandbox = await self._get_sandbox(sandbox_id)
        normalized_path = self.normalize_path(path)

        content_bytes = await self._retry_operation(
            sandbox.files.read, normalized_path, format="bytes"
        )
        content, is_binary = self._encode_file_content(path, content_bytes)

        return FileContent(
            path=path,
            content=content,
            type="file",
            is_binary=is_binary,
        )

    async def create_pty(
        self,
        sandbox_id: str,
        rows: int,
        cols: int,
        on_data: PtyDataCallbackType | None = None,
    ) -> PtySession:
        sandbox = await self._get_sandbox(sandbox_id)
        session_id = str(uuid.uuid4())

        pty = await self._retry_operation(
            sandbox.pty.create,
            size=E2BPtySize(rows=rows, cols=cols),
            on_data=lambda data: on_data(normalize_e2b_pty_data(data))
            if on_data
            else None,
            cwd="/home/user",
            envs={"TERM": "xterm-256color"},
            timeout=None,
        )

        self._register_pty_session(
            sandbox_id,
            session_id,
            {
                "pty": pty,
                "sandbox": sandbox,
            },
        )

        return PtySession(
            id=session_id,
            pid=pty.pid,
            rows=rows,
            cols=cols,
        )

    async def send_pty_input(
        self,
        sandbox_id: str,
        pty_id: str,
        data: bytes,
    ) -> None:
        session = self._get_pty_session(sandbox_id, pty_id)
        if not session:
            return

        try:
            sandbox = session.get("sandbox")
            if sandbox is None:
                sandbox = await self._get_sandbox(sandbox_id)
                session["sandbox"] = sandbox
            pty = session["pty"]
            await sandbox.pty.send_stdin(pty.pid, data)
        except Exception as e:
            logger.error("Failed to send PTY input: %s", e)
            session["sandbox"] = None
            await self.kill_pty(sandbox_id, pty_id)

    async def resize_pty(
        self,
        sandbox_id: str,
        pty_id: str,
        size: PtySize,
    ) -> None:
        session = self._get_pty_session(sandbox_id, pty_id)
        if not session:
            return

        rows = max(size.rows, 1)
        cols = max(size.cols, 1)

        try:
            sandbox = session.get("sandbox")
            if sandbox is None:
                sandbox = await self._get_sandbox(sandbox_id)
                session["sandbox"] = sandbox
            pty = session["pty"]
            await self._retry_operation(
                sandbox.pty.resize, pty.pid, E2BPtySize(rows=rows, cols=cols)
            )
        except Exception as e:
            logger.error(
                "Failed to resize PTY for sandbox %s: %s", sandbox_id, e, exc_info=True
            )
            session["sandbox"] = None

    async def kill_pty(
        self,
        sandbox_id: str,
        pty_id: str,
    ) -> None:
        session = self._get_pty_session(sandbox_id, pty_id)
        if not session:
            return

        self._cleanup_pty_session_tracking(sandbox_id, pty_id)

        try:
            pty = session["pty"]
            await self._retry_operation(pty.kill)
        except Exception as e:
            logger.error(
                "Error killing PTY process for session %s: %s", pty_id, e, exc_info=True
            )

    async def get_preview_links(self, sandbox_id: str) -> list[PreviewLink]:
        sandbox = await self._get_sandbox(sandbox_id)

        result = await self._retry_operation(
            sandbox.commands.run,
            LISTENING_PORTS_COMMAND,
            timeout=5,
        )

        listening_ports = self._parse_listening_ports(result.stdout)

        return self._build_preview_links(
            listening_ports=listening_ports,
            url_builder=lambda port: f"https://{port}-{sandbox_id}.e2b.dev",
            excluded_ports=EXCLUDED_PREVIEW_PORTS,
        )

    async def get_ide_url(self, sandbox_id: str) -> str | None:
        openvscode_port = 8765
        return f"https://{openvscode_port}-{sandbox_id}.e2b.dev/?folder=/home/user"

    async def _get_sandbox(self, sandbox_id: str) -> AsyncSandbox:
        if sandbox_id in self._active_sandboxes:
            sandbox = self._active_sandboxes[sandbox_id]
            if await self._retry_operation(sandbox.is_running):
                return sandbox
            del self._active_sandboxes[sandbox_id]

        sandbox = await self._retry_operation(
            AsyncSandbox.connect,
            sandbox_id=sandbox_id,
            api_key=self.api_key,
            auto_pause=True,
            timeout=SANDBOX_AUTO_PAUSE_TIMEOUT,
        )
        self._active_sandboxes[sandbox_id] = sandbox
        return sandbox

    async def _retry_operation(
        self, operation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        async for attempt in AsyncRetrying(**RETRY_CONFIG):
            with attempt:
                return await operation(*args, **kwargs)
