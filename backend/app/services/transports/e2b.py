import asyncio
import logging
from collections.abc import AsyncIterable
from contextlib import suppress
from typing import Any

from claude_agent_sdk._errors import CLIConnectionError, ProcessError
from claude_agent_sdk.types import ClaudeAgentOptions
from e2b import AsyncSandbox
from e2b.sandbox.commands.command_handle import CommandExitException
from e2b.sandbox_async.commands.command_handle import AsyncCommandHandle

from app.constants import SANDBOX_AUTO_PAUSE_TIMEOUT
from app.services.transports.base import BaseSandboxTransport

logger = logging.getLogger(__name__)


class E2BSandboxTransport(BaseSandboxTransport):
    def __init__(
        self,
        *,
        sandbox_id: str,
        api_key: str,
        prompt: str | AsyncIterable[dict[str, Any]],
        options: ClaudeAgentOptions,
    ) -> None:
        super().__init__(sandbox_id=sandbox_id, prompt=prompt, options=options)
        self._api_key = api_key
        self._sandbox: AsyncSandbox | None = None
        self._command: AsyncCommandHandle | None = None

    def _get_logger(self) -> Any:
        return logger

    async def connect(self) -> None:
        if self._ready:
            return
        self._stdin_closed = False
        try:
            self._sandbox = await AsyncSandbox.connect(
                sandbox_id=self._sandbox_id,
                api_key=self._api_key,
                auto_pause=True,
                timeout=SANDBOX_AUTO_PAUSE_TIMEOUT,
            )
        except Exception as exc:
            raise CLIConnectionError(
                f"Failed to connect to sandbox {self._sandbox_id}: {exc}"
            ) from exc

        command_line = self._build_command()
        envs, cwd, user = self._prepare_environment()

        async def on_stdout(data: str) -> None:
            await self._stdout_queue.put(data)

        async def on_stderr(data: str) -> None:
            if self._options.stderr:
                try:
                    self._options.stderr(data)
                except Exception:
                    pass

        try:
            assert self._sandbox is not None
            self._command = await self._sandbox.commands.run(
                command_line,
                background=True,
                envs={key: str(value) for key, value in envs.items()},
                cwd=cwd,
                user=user,
                timeout=0,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
        except Exception as exc:
            raise CLIConnectionError(f"Failed to start Claude CLI: {exc}") from exc
        loop = asyncio.get_running_loop()
        self._monitor_task = loop.create_task(self._monitor_process())
        self._ready = True

    def _is_connection_ready(self) -> bool:
        return self._command is not None and self._sandbox is not None

    async def _cleanup_resources(self) -> None:
        if self._command:
            with suppress(Exception):
                await self._command.kill()
            self._command = None

    async def _send_data(self, data: str) -> None:
        assert self._sandbox is not None and self._command is not None
        await self._sandbox.commands.send_stdin(self._command.pid, data)

    async def _send_eof(self) -> None:
        assert self._sandbox is not None and self._command is not None
        await self._sandbox.commands.send_stdin(self._command.pid, "\u0004")

    async def _monitor_process(self) -> None:
        if not self._command:
            return
        try:
            await self._command.wait()
        except CommandExitException as exc:
            self._exit_error = ProcessError(
                "Claude CLI exited with an error",
                exit_code=exc.exit_code,
                stderr=exc.stderr,
            )
        except Exception as exc:
            self._exit_error = CLIConnectionError(
                f"Claude CLI stopped unexpectedly: {exc}"
            )
        finally:
            await self._put_sentinel()
            self._ready = False
