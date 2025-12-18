import asyncio
import base64
import io
import json
import logging
import operator
import posixpath
import shlex
import uuid
import zipfile
from asyncio import QueueEmpty, QueueFull
from contextlib import suppress
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Coroutine

from e2b import AsyncSandbox
from e2b.sandbox.commands.command_handle import PtySize
from fastapi import WebSocket
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.constants import SANDBOX_AUTO_PAUSE_TIMEOUT
from app.core.config import get_settings
from app.models.types import (
    CustomAgentDict,
    CustomEnvVarDict,
    CustomSkillDict,
    CustomSlashCommandDict,
)
from app.services.agent import AgentService
from app.services.command import CommandService
from app.services.exceptions import ErrorCode, SandboxException
from app.services.skill import SkillService

logger = logging.getLogger(__name__)

SANDBOX_DEFAULT_TIMEOUT = 3600
SANDBOX_DEFAULT_COMMAND_TIMEOUT = 120
MAX_CHECKPOINTS_PER_SANDBOX = 20
CHECKPOINT_BASE_DIR = "/home/user/.checkpoints"
OPENVSCODE_PORT = 8765
OPENVSCODE_SETTINGS_DIR = "/home/user/.openvscode-server/data/Machine"
OPENVSCODE_SETTINGS_PATH = f"{OPENVSCODE_SETTINGS_DIR}/settings.json"
OPENVSCODE_DEFAULT_SETTINGS: dict[str, object] = {
    "workbench.colorTheme": "Default Dark Modern",
    "window.autoDetectColorScheme": True,
    "workbench.preferredDarkColorTheme": "Default Dark Modern",
    "workbench.preferredLightColorTheme": "Default Light Modern",
    "editor.fontSize": 12,
    "editor.minimap.enabled": True,
    "editor.wordWrap": "on",
    "telemetry.telemetryLevel": "off",
}
EXCLUDED_PREVIEW_PORTS = ["49982", "49983", "22", "4040", "3456", "8765"]
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


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

SYSTEM_VARIABLES: list[str] = [
    "SHELL",
    "PWD",
    "LOGNAME",
    "HOME",
    "USER",
    "SHLVL",
    "PS1",
    "PATH",
    "E2B_SANDBOX",
    "_",
]

RESTORE_EXCLUDE_PATTERNS: list[str] = [
    ".checkpoints",
    ".cache",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.log",
    ".DS_Store",
    "dist",
    "build",
    ".next",
    ".nuxt",
]

EXCLUDED_PATHS: list[str] = [
    "*/node_modules/*",
    "*/node_modules",
    "*/.*",
    "*/__pycache__/*",
    "*/__pycache__",
    "*.pyc",
    "*.log",
    "*/dist/*",
    "*/dist",
    "*/build/*",
    "*/build",
    "package-lock.json",
    "*/package-lock.json",
    "bun.lock",
    "*/bun.lock",
]

settings = get_settings()


BINARY_EXTENSIONS: set[str] = {
    "exe",
    "dll",
    "so",
    "dylib",
    "a",
    "lib",
    "obj",
    "o",
    "zip",
    "tar",
    "gz",
    "bz2",
    "xz",
    "7z",
    "rar",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "bmp",
    "ico",
    "tiff",
    "webp",
    "svg",
    "mp4",
    "avi",
    "mkv",
    "mov",
    "wmv",
    "flv",
    "webm",
    "mp3",
    "wav",
    "flac",
    "ogg",
    "wma",
    "aac",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "bin",
    "dat",
    "db",
    "sqlite",
    "sqlite3",
    "woff",
    "woff2",
    "ttf",
    "otf",
    "eot",
    "class",
    "jar",
    "war",
    "ear",
    "pyc",
    "pyo",
    "pyd",
}


class PtyDataCallback:
    def __init__(
        self, service: "SandboxService", output_queue: "asyncio.Queue[str]"
    ) -> None:
        self.service = service
        self.output_queue = output_queue

    async def __call__(self, data: Any) -> None:
        await self.service._enqueue_pty_output(data, self.output_queue)


class BackgroundOutputCallback:
    def __init__(self, output_list: list[str], prefix: str) -> None:
        self.output_list = output_list
        self.prefix = prefix

    def __call__(self, data: Any) -> None:
        self.output_list.append(f"[{self.prefix}] {data}\n")


class SandboxService:
    def __init__(
        self,
        e2b_api_key: str | None = None,
        session_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = e2b_api_key
        self.session_factory = session_factory
        self._active_sandboxes: dict[str, AsyncSandbox] = {}
        self._active_pty_sessions: dict[str, dict[str, Any]] = {}

    async def __aenter__(self) -> "SandboxService":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        try:
            await self.cleanup()
        except Exception as cleanup_error:
            logger.error(
                "Error during SandboxService cleanup: %s", cleanup_error, exc_info=True
            )
            if exc_type is None:
                raise
        return False

    @staticmethod
    def _validate_message_id(message_id: str) -> None:
        try:
            uuid.UUID(message_id)
        except ValueError:
            raise SandboxException(f"Invalid message_id format: {message_id}")

    async def cleanup(self) -> None:
        for sandbox_id in list(self._active_pty_sessions.keys()):
            for session_id in list(self._active_pty_sessions[sandbox_id].keys()):
                try:
                    await self.cleanup_pty_session(sandbox_id, session_id)
                except Exception as e:
                    logger.warning(
                        "Failed to cleanup PTY session %s for sandbox %s: %s",
                        session_id,
                        sandbox_id,
                        e,
                    )

    async def create_sandbox(self) -> str:
        if not self.api_key:
            raise SandboxException("E2B API key is required")

        try:
            sandbox = await self._retry_operation(
                AsyncSandbox.create,
                timeout=SANDBOX_DEFAULT_TIMEOUT,
                api_key=self.api_key,
                template=settings.E2B_TEMPLATE_ID,
                auto_pause=True,
            )
        except SandboxException:
            raise
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

    async def delete_sandbox(self, sandbox_id: str) -> None:
        if not sandbox_id:
            return
        asyncio.create_task(self._delete_sandbox_deferred(sandbox_id))

    async def _delete_sandbox_deferred(self, sandbox_id: str) -> None:
        try:
            sandbox = self._active_sandboxes.get(sandbox_id)
            if not sandbox:
                try:
                    if self.api_key:
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

        except Exception as e:
            logger.warning(
                "Failed to delete sandbox %s: %s",
                sandbox_id,
                e,
                exc_info=True,
                extra={"sandbox_id": sandbox_id},
            )

    async def get_or_connect_sandbox(self, sandbox_id: str) -> AsyncSandbox:
        if sandbox_id in self._active_sandboxes:
            sandbox = self._active_sandboxes[sandbox_id]
            if await self._retry_operation(sandbox.is_running):
                return sandbox
            else:
                del self._active_sandboxes[sandbox_id]

        if not self.api_key:
            raise SandboxException("E2B API key is required")

        sandbox = await self._retry_operation(
            AsyncSandbox.connect,
            sandbox_id=sandbox_id,
            api_key=self.api_key,
            auto_pause=True,
            timeout=SANDBOX_AUTO_PAUSE_TIMEOUT,
        )
        self._active_sandboxes[sandbox_id] = sandbox
        return sandbox

    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        background: bool = False,
    ) -> str:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        envs = await self._build_env_map(sandbox_id, sandbox)

        if not background:
            return await self._run_foreground_command(sandbox, command, envs)

        process, initial_output = await self._execute_background_command(
            sandbox, command, envs
        )

        if initial_output:
            output_text = "".join(initial_output)
            return (
                f"Background process started (PID: {process.pid})\n\n"
                f"Initial output:\n{output_text}"
            )

        return f"Background process started (PID: {process.pid})"

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        normalized_path = self.normalize_path(file_path)
        await self._retry_operation(sandbox.files.write, normalized_path, content)

    async def get_preview_links(self, sandbox_id: str) -> list[dict[str, str | int]]:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)

        result = await self._retry_operation(
            sandbox.commands.run,
            "ss -tuln | grep LISTEN | awk '{print $5}' | sed 's/.*://g' | grep -E '^[0-9]+$' | sort -u",
            timeout=5,
        )

        ports = result.stdout.strip().splitlines()

        preview_links: list[dict[str, str | int]] = []
        for port in ports:
            if not port or port in EXCLUDED_PREVIEW_PORTS:
                continue

            try:
                port_num = int(port)
                preview_url = f"https://{port_num}-{sandbox_id}.e2b.dev"
                preview_links.append(
                    {
                        "preview_url": preview_url,
                        "port": port_num,
                    }
                )
            except ValueError:
                pass

        return preview_links

    def _create_pty_data_callback(
        self, output_queue: "asyncio.Queue[str]"
    ) -> "PtyDataCallback":
        return PtyDataCallback(self, output_queue)

    async def create_pty_session(
        self, sandbox_id: str, rows: int = 24, cols: int = 80
    ) -> dict[str, Any]:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        session_id = str(uuid.uuid4())
        output_queue: "asyncio.Queue[str]" = asyncio.Queue(maxsize=512)

        pty = await self._retry_operation(
            sandbox.pty.create,
            size=PtySize(rows=rows, cols=cols),
            on_data=self._create_pty_data_callback(output_queue),
            cwd="/home/user",
            envs={"TERM": "xterm-256color"},
            timeout=None,
        )

        if sandbox_id not in self._active_pty_sessions:
            self._active_pty_sessions[sandbox_id] = {}

        self._active_pty_sessions[sandbox_id][session_id] = {
            "pty": pty,
            "sandbox": sandbox,
            "output_queue": output_queue,
            "size": {"rows": rows, "cols": cols},
        }

        return {"id": session_id, "rows": rows, "cols": cols}

    async def send_pty_input(
        self, sandbox_id: str, pty_session_id: str, data: str | bytes
    ) -> None:
        session = self._get_pty_session_data(sandbox_id, pty_session_id)
        if not session:
            return

        data_bytes = data.encode() if isinstance(data, str) else data

        try:
            sandbox = session.get("sandbox")
            if sandbox is None:
                sandbox = await self.get_or_connect_sandbox(sandbox_id)
                session["sandbox"] = sandbox
            pty = session["pty"]
            await sandbox.pty.send_stdin(pty.pid, data_bytes)
        except Exception as e:
            logger.error("Failed to send PTY input: %s", e)
            session["sandbox"] = None
            await self.cleanup_pty_session(sandbox_id, pty_session_id)

    async def resize_pty_session(
        self, sandbox_id: str, pty_session_id: str, rows: int, cols: int
    ) -> None:
        session = self._get_pty_session_data(sandbox_id, pty_session_id)
        if not session:
            return

        rows = max(rows, 1)
        cols = max(cols, 1)

        try:
            sandbox = session.get("sandbox")
            if sandbox is None:
                sandbox = await self.get_or_connect_sandbox(sandbox_id)
                session["sandbox"] = sandbox
            pty = session["pty"]
            await self._retry_operation(
                sandbox.pty.resize, pty.pid, PtySize(rows=rows, cols=cols)
            )
            session["size"] = {"rows": rows, "cols": cols}
        except Exception as e:
            logger.error(
                "Failed to resize PTY for sandbox %s: %s", sandbox_id, e, exc_info=True
            )
            session["sandbox"] = None

    async def forward_pty_output(
        self, sandbox_id: str, pty_session_id: str, websocket: WebSocket
    ) -> None:
        session = self._get_pty_session_data(sandbox_id, pty_session_id)
        if not session:
            return

        output_queue = session["output_queue"]

        try:
            while True:
                chunk = await output_queue.get()
                buffer = [chunk]

                while True:
                    try:
                        buffer.append(output_queue.get_nowait())
                    except QueueEmpty:
                        break

                payload = json.dumps({"type": "stdout", "data": "".join(buffer)})
                await websocket.send_text(payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                "Error forwarding PTY output for sandbox %s: %s",
                sandbox_id,
                e,
                exc_info=True,
            )

    async def cleanup_pty_session(self, sandbox_id: str, pty_session_id: str) -> None:
        session = self._get_pty_session_data(sandbox_id, pty_session_id)
        if not session:
            return

        try:
            del self._active_pty_sessions[sandbox_id][pty_session_id]
            if not self._active_pty_sessions[sandbox_id]:
                del self._active_pty_sessions[sandbox_id]
        except Exception as e:
            logger.error(
                "Error cleaning up PTY session %s: %s", pty_session_id, e, exc_info=True
            )

        try:
            pty = session["pty"]
            await self._retry_operation(pty.kill)
        except Exception as e:
            logger.error(
                "Error killing PTY process for session %s: %s",
                pty_session_id,
                e,
                exc_info=True,
            )

    async def get_files_metadata(self, sandbox_id: str) -> list[dict[str, Any]]:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)

        exclude_conditions = []
        for pattern in EXCLUDED_PATHS:
            if pattern.startswith("*."):
                exclude_conditions.append(f"-not -name '{pattern}'")
            else:
                exclude_conditions.append(f"-not -path '{pattern}'")

        exclude_args = " ".join(exclude_conditions)

        find_command = f"""
        find /home/user {exclude_args} -printf '%p\t%y\t%s\t%T@\n'
        """

        result = await self._retry_operation(
            sandbox.commands.run, find_command, timeout=30
        )

        metadata_items = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 4:
                continue

            path, file_type, size, mtime = parts[0], parts[1], parts[2], parts[3]

            if not path or path == "/home/user" or path == "":
                continue

            if path.startswith("/home/user/"):
                path = path[11:]
            elif path.startswith("/home/user"):
                path = path[10:]

            if file_type == "f":
                is_binary = Path(path).suffix.lstrip(".").lower() in BINARY_EXTENSIONS
                metadata_items.append(
                    {
                        "path": path,
                        "type": "file",
                        "is_binary": is_binary,
                        "size": int(size) if size.isdigit() else 0,
                        "modified": (
                            float(mtime) if mtime.replace(".", "").isdigit() else 0
                        ),
                    }
                )
            elif file_type == "d":
                metadata_items.append(
                    {
                        "path": path,
                        "type": "directory",
                        "size": 0,
                        "modified": (
                            float(mtime) if mtime.replace(".", "").isdigit() else 0
                        ),
                    }
                )

        return metadata_items

    async def get_file_content(self, sandbox_id: str, file_path: str) -> dict[str, Any]:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)

        try:
            content, is_binary = await self._read_file_content(sandbox, file_path)
            return {
                "path": file_path,
                "content": content,
                "type": "file",
                "is_binary": is_binary,
            }
        except Exception as e:
            raise SandboxException(f"Failed to read file {file_path}: {str(e)}")

    async def add_secret(
        self,
        sandbox_id: str,
        key: str,
        value: str,
    ) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        export_command = self._format_export_command(key, value)
        await self._append_to_bashrc(sandbox, export_command)
        await self._source_bashrc(sandbox)

    async def update_secret(
        self,
        sandbox_id: str,
        key: str,
        value: str,
    ) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        await self._remove_from_bashrc(sandbox, key)
        export_command = self._format_export_command(key, value)
        await self._append_to_bashrc(sandbox, export_command)
        await self._source_bashrc(sandbox)

    async def delete_secret(
        self,
        sandbox_id: str,
        key: str,
    ) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        await self._remove_from_bashrc(sandbox, key)

    async def get_secrets(
        self,
        sandbox_id: str,
        *,
        sandbox: AsyncSandbox | None = None,
    ) -> list[dict[str, Any]]:
        sandbox_obj = sandbox or await self.get_or_connect_sandbox(sandbox_id)

        result = await self._retry_operation(
            sandbox_obj.commands.run,
            "grep '^export' ~/.bashrc | sed 's/^export //g'",
            timeout=5,
        )

        env_lines = result.stdout.strip().split("\n")
        secrets = []

        for line in env_lines:
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip('"').strip("'")

                if key not in SYSTEM_VARIABLES:
                    secrets.append(
                        {
                            "key": key,
                            "value": value,
                        }
                    )

        return secrets

    async def generate_zip_download(self, sandbox_id: str) -> bytes:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)

        metadata_items = await self.get_files_metadata(sandbox_id)

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for item in metadata_items:
                if item["type"] == "file":
                    file_path = item["path"]

                    try:
                        content, is_binary = await self._read_file_content(
                            sandbox, file_path
                        )

                        if is_binary:
                            zip_file.writestr(file_path, base64.b64decode(content))
                        else:
                            zip_file.writestr(file_path, content.encode("utf-8"))
                    except Exception as e:
                        logger.warning(
                            "Failed to write file %s to zip: %s", file_path, e
                        )
                        continue

        zip_buffer.seek(0)
        return zip_buffer.read()

    async def _copy_all_resources_to_sandbox(
        self,
        sandbox_id: str,
        user_id: str,
        custom_skills: list[CustomSkillDict] | None,
        custom_slash_commands: list[CustomSlashCommandDict] | None,
        custom_agents: list[CustomAgentDict] | None,
    ) -> None:
        skill_service = SkillService()
        command_service = CommandService()
        agent_service = AgentService()

        enabled_skills = skill_service.get_enabled(user_id, custom_skills or [])
        enabled_commands = command_service.get_enabled(
            user_id, custom_slash_commands or []
        )
        enabled_agents = agent_service.get_enabled(user_id, custom_agents or [])

        if not enabled_skills and not enabled_commands and not enabled_agents:
            return

        zip_buffer = io.BytesIO()
        has_content = False

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for skill in enabled_skills:
                skill_name = skill["name"]
                local_zip_path = Path(skill["path"])

                if not local_zip_path.exists():
                    logger.warning(
                        "Skill ZIP not found: %s at %s", skill_name, local_zip_path
                    )
                    continue

                with zipfile.ZipFile(local_zip_path, "r") as skill_zip:
                    for item in skill_zip.namelist():
                        content = skill_zip.read(item)
                        zf.writestr(f".claude/skills/{skill_name}/{item}", content)
                        has_content = True

            for command in enabled_commands:
                command_name = command["name"]
                local_path = Path(command["path"])

                if not local_path.exists():
                    logger.warning(
                        "Command not found: %s at %s", command_name, local_path
                    )
                    continue

                command_content = local_path.read_text(encoding="utf-8")
                zf.writestr(f".claude/commands/{command_name}.md", command_content)
                has_content = True

            for agent in enabled_agents:
                agent_name = agent["name"]
                local_path = Path(agent["path"])

                if not local_path.exists():
                    logger.warning("Agent not found: %s at %s", agent_name, local_path)
                    continue

                agent_content = local_path.read_text(encoding="utf-8")
                zf.writestr(f".claude/agents/{agent_name}.md", agent_content)
                has_content = True

        if not has_content:
            return

        zip_buffer.seek(0)
        zip_content = zip_buffer.getvalue()
        encoded_content = base64.b64encode(zip_content).decode("utf-8")

        remote_zip_path = f"/home/user/_resources_{uuid.uuid4().hex[:8]}.zip"
        temp_b64_path = f"{remote_zip_path}.b64tmp"

        try:
            await self.write_file(sandbox_id, temp_b64_path, encoded_content)
            decode_and_extract_cmd = (
                f"base64 -d {shlex.quote(temp_b64_path)} > {shlex.quote(remote_zip_path)} && "
                f"unzip -q -o {shlex.quote(remote_zip_path)} -d /home/user && "
                f"rm -f {shlex.quote(remote_zip_path)} {shlex.quote(temp_b64_path)}"
            )
            await self.execute_command(sandbox_id, decode_and_extract_cmd)

            resource_count = (
                len(enabled_skills) + len(enabled_commands) + len(enabled_agents)
            )
            logger.info(
                "Copied %d resources to sandbox %s in single upload",
                resource_count,
                sandbox_id,
            )
        except Exception as e:
            logger.error("Failed to copy resources to sandbox %s: %s", sandbox_id, e)
            cleanup_cmd = (
                f"rm -f {shlex.quote(remote_zip_path)} {shlex.quote(temp_b64_path)}"
            )
            try:
                await self.execute_command(sandbox_id, cleanup_cmd)
            except Exception:
                pass
            raise SandboxException(f"Failed to copy resources to sandbox: {e}") from e

    async def _add_env_vars_parallel(
        self, sandbox_id: str, custom_env_vars: list[CustomEnvVarDict]
    ) -> None:
        if not custom_env_vars:
            return
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        exports = [
            self._format_export_command(env_var["key"], env_var["value"])
            for env_var in custom_env_vars
        ]
        combined = " && ".join(f'echo "{exp}" >> ~/.bashrc' for exp in exports)
        await self._retry_operation(sandbox.commands.run, combined, timeout=10)
        await self._source_bashrc(sandbox)

    async def _setup_github_token(self, sandbox_id: str, github_token: str) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        script_content = '#!/bin/sh\\necho "$GITHUB_TOKEN"'
        export_token = self._format_export_command("GITHUB_TOKEN", github_token)
        export_askpass = self._format_export_command(
            "GIT_ASKPASS", "/home/user/.git-askpass.sh"
        )
        combined_cmd = (
            f"echo -e '{script_content}' > /home/user/.git-askpass.sh && "
            f"chmod +x /home/user/.git-askpass.sh && "
            f'echo "{export_token}" >> ~/.bashrc && '
            f'echo "{export_askpass}" >> ~/.bashrc'
        )
        await self._retry_operation(sandbox.commands.run, combined_cmd, timeout=10)
        await self._source_bashrc(sandbox)

    async def _setup_anthropic_bridge(
        self, sandbox_id: str, openrouter_api_key: str
    ) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        export_cmd = self._format_export_command(
            "OPENROUTER_API_KEY", openrouter_api_key
        )
        await self._append_to_bashrc(sandbox, export_cmd)
        await self._source_bashrc(sandbox)

        start_cmd = f"OPENROUTER_API_KEY={shlex.quote(openrouter_api_key)} anthropic-bridge --port 3456 --host 0.0.0.0"
        start_result = await self.execute_command(
            sandbox_id, start_cmd, background=True
        )
        logger.info("Anthropic Bridge started: %s", start_result)

    async def _start_openvscode_server(self, sandbox_id: str) -> None:
        sandbox = await self.get_or_connect_sandbox(sandbox_id)
        settings_content = json.dumps(OPENVSCODE_DEFAULT_SETTINGS, indent=2)
        escaped_settings = settings_content.replace("'", "'\"'\"'")

        setup_and_start_cmd = (
            f"mkdir -p {OPENVSCODE_SETTINGS_DIR} && "
            f"echo '{escaped_settings}' > {OPENVSCODE_SETTINGS_PATH} && "
            f"openvscode-server --host 0.0.0.0 --port {OPENVSCODE_PORT} "
            "--without-connection-token --disable-telemetry"
        )
        process = await self._retry_operation(
            sandbox.commands.run,
            setup_and_start_cmd,
            background=True,
            timeout=None,
        )
        logger.info("OpenVSCode Server started: PID %s", process.pid)

    async def update_ide_theme(self, sandbox_id: str, theme: str) -> None:
        vscode_theme = (
            "Default Dark Modern" if theme == "dark" else "Default Light Modern"
        )
        settings = {
            **OPENVSCODE_DEFAULT_SETTINGS,
            "workbench.colorTheme": vscode_theme,
            "window.autoDetectColorScheme": False,
        }
        settings_content = json.dumps(settings, indent=2)
        await self.write_file(sandbox_id, OPENVSCODE_SETTINGS_PATH, settings_content)
        logger.info("IDE theme updated to: %s", vscode_theme)

    async def initialize_sandbox(
        self,
        sandbox_id: str,
        github_token: str | None = None,
        openrouter_api_key: str | None = None,
        custom_env_vars: list[CustomEnvVarDict] | None = None,
        custom_skills: list[CustomSkillDict] | None = None,
        custom_slash_commands: list[CustomSlashCommandDict] | None = None,
        custom_agents: list[CustomAgentDict] | None = None,
        user_id: str | None = None,
    ) -> None:
        tasks: list[Coroutine[None, None, None]] = [
            self._start_openvscode_server(sandbox_id),
        ]

        if custom_env_vars:
            tasks.append(self._add_env_vars_parallel(sandbox_id, custom_env_vars))

        if openrouter_api_key:
            tasks.append(self._setup_anthropic_bridge(sandbox_id, openrouter_api_key))

        has_resources = (
            custom_skills or custom_slash_commands or custom_agents
        ) and user_id
        if has_resources:
            tasks.append(
                self._copy_all_resources_to_sandbox(
                    sandbox_id,
                    user_id,  # type: ignore[arg-type]
                    custom_skills,
                    custom_slash_commands,
                    custom_agents,
                )
            )

        if github_token:
            tasks.append(self._setup_github_token(sandbox_id, github_token))

        await asyncio.gather(*tasks)

    async def create_checkpoint(self, sandbox_id: str, message_id: str) -> str | None:
        # Creates a space-efficient incremental checkpoint using rsync hard links.
        # The --link-dest option creates hard links to unchanged files from the previous
        # checkpoint, meaning only modified files consume additional disk space.
        # For example, if checkpoint A has 100 files and checkpoint B only changes 2 files,
        # B will hard-link 98 files to A and only store 2 new copies.
        self._validate_message_id(message_id)

        checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{message_id}"

        await self.execute_command(
            sandbox_id, f"mkdir -p {shlex.quote(CHECKPOINT_BASE_DIR)}"
        )

        prev_checkpoint = await self._get_latest_checkpoint_dir(sandbox_id)

        exclude_args = " ".join(
            f"--exclude={shlex.quote(pattern)}" for pattern in RESTORE_EXCLUDE_PATTERNS
        )

        if prev_checkpoint:
            # Use --link-dest for incremental backup: unchanged files become hard links
            rsync_cmd = (
                f"rsync -a --delete "
                f"--link-dest={shlex.quote(prev_checkpoint)} "
                f"{exclude_args} "
                f"/home/user/ {shlex.quote(checkpoint_dir)}/"
            )
        else:
            rsync_cmd = (
                f"rsync -a --delete "
                f"{exclude_args} "
                f"/home/user/ {shlex.quote(checkpoint_dir)}/"
            )

        try:
            await self.execute_command(sandbox_id, rsync_cmd)
        except Exception as e:
            logger.error("Checkpoint creation failed for %s: %s", message_id, e)
            try:
                await self.execute_command(
                    sandbox_id, f"rm -rf {shlex.quote(checkpoint_dir)}"
                )
                logger.info("Cleaned up partial checkpoint %s", message_id)
            except Exception as cleanup_error:
                logger.warning(
                    "Failed to cleanup partial checkpoint %s: %s",
                    message_id,
                    cleanup_error,
                )
            raise

        await self._cleanup_old_checkpoints(sandbox_id)

        return message_id

    async def restore_checkpoint(self, sandbox_id: str, message_id: str) -> bool:
        self._validate_message_id(message_id)

        checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{message_id}"

        check_cmd = f'[ -d {shlex.quote(checkpoint_dir)} ] && echo "1" || echo "0"'
        result = await self.execute_command(sandbox_id, check_cmd)

        if result.strip() != "1":
            raise FileNotFoundError(f"Checkpoint {message_id} not found")

        exclude_args = " ".join(
            f"--exclude={shlex.quote(pattern)}" for pattern in RESTORE_EXCLUDE_PATTERNS
        )

        rsync_cmd = (
            f"rsync -a --delete "
            f"{exclude_args} "
            f"--stats "
            f"{shlex.quote(checkpoint_dir)}/ /home/user/"
        )

        await self.execute_command(sandbox_id, rsync_cmd)

        return True

    async def list_checkpoints(self, sandbox_id: str) -> list[dict[str, Any]]:
        check_cmd = f'[ -d {shlex.quote(CHECKPOINT_BASE_DIR)} ] && echo "1" || echo "0"'
        result = await self.execute_command(sandbox_id, check_cmd)

        if result.strip() != "1":
            return []

        list_cmd = (
            f"cd {shlex.quote(CHECKPOINT_BASE_DIR)} && "
            f"for dir in */; do "
            f'if [ -d "$dir" ]; then '
            f'echo "${{dir%/}}|$(stat -c %Y "$dir")"; '
            f"fi; "
            f"done"
        )

        result = await self.execute_command(sandbox_id, list_cmd)

        if not result.strip():
            return []

        checkpoints = []
        for line in result.strip().split("\n"):
            if "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) != 2:
                continue

            message_id, timestamp = parts
            checkpoints.append(
                {
                    "message_id": message_id,
                    "created_at": datetime.fromtimestamp(int(timestamp)).isoformat(),
                }
            )

        checkpoints.sort(key=operator.itemgetter("created_at"), reverse=True)
        return checkpoints

    async def _get_latest_checkpoint_dir(self, sandbox_id: str) -> str | None:
        checkpoints = await self.list_checkpoints(sandbox_id)
        if not checkpoints:
            return None
        return f"{CHECKPOINT_BASE_DIR}/{checkpoints[0]['message_id']}"

    async def _cleanup_old_checkpoints(self, sandbox_id: str) -> int:
        checkpoints = await self.list_checkpoints(sandbox_id)

        if len(checkpoints) <= MAX_CHECKPOINTS_PER_SANDBOX:
            return 0

        to_delete = checkpoints[MAX_CHECKPOINTS_PER_SANDBOX:]
        deleted_count = 0

        for checkpoint in to_delete:
            message_id = checkpoint["message_id"]
            checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{message_id}"

            await self.execute_command(
                sandbox_id, f"rm -rf {shlex.quote(checkpoint_dir)}"
            )
            deleted_count += 1
        return deleted_count

    async def restore_to_message(self, sandbox_id: str, message_id: str) -> bool:
        checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{message_id}"

        check_cmd = f'[ -d {shlex.quote(checkpoint_dir)} ] && echo "1" || echo "0"'
        result = await self.execute_command(sandbox_id, check_cmd)

        if result.strip() == "1":
            return await self.restore_checkpoint(sandbox_id, message_id)

        raise SandboxException(f"Checkpoint not found for message {message_id}")

    async def _enqueue_pty_output(
        self, data: Any, output_queue: "asyncio.Queue[str]"
    ) -> None:
        # Handles PTY output with backpressure management.
        # When the queue is full (consumer not keeping up), we drop the oldest item
        # rather than blocking or losing the newest data. This prevents the PTY from
        # stalling while ensuring the most recent output is always available.
        try:
            if hasattr(data, "data"):
                decoded = data.data.decode("utf-8", errors="replace")
            elif isinstance(data, bytes):
                decoded = data.decode("utf-8", errors="replace")
            else:
                decoded = str(data)
            output_queue.put_nowait(decoded)
        except QueueFull:
            # Queue overflow: discard oldest item to make room for new data
            with suppress(QueueEmpty):
                _ = output_queue.get_nowait()
            output_queue.put_nowait(decoded)
        except Exception as e:
            logger.error("Error handling PTY output: %s", e, exc_info=True)

    def _get_pty_session_data(
        self, sandbox_id: str, session_id: str
    ) -> dict[str, Any] | None:
        return self._active_pty_sessions.get(sandbox_id, {}).get(session_id)

    async def _read_file_content(
        self,
        sandbox: AsyncSandbox,
        file_path: str,
    ) -> tuple[str, bool]:
        normalized_path = self.normalize_path(file_path)
        is_binary = Path(file_path).suffix.lstrip(".").lower() in BINARY_EXTENSIONS

        if is_binary:
            content_bytes = await self._retry_operation(
                sandbox.files.read, normalized_path, format="bytes"
            )
            content = base64.b64encode(content_bytes).decode("utf-8")
        else:
            content = await self._retry_operation(
                sandbox.files.read, normalized_path, format="text"
            )

        return content, is_binary

    async def _build_env_map(
        self, sandbox_id: str, sandbox: AsyncSandbox | None = None
    ) -> dict[str, str]:
        secrets = await self.get_secrets(sandbox_id, sandbox=sandbox)
        return {item["key"]: item["value"] for item in secrets}

    async def _run_foreground_command(
        self,
        sandbox: AsyncSandbox,
        command: str,
        envs: dict[str, str],
    ) -> str:
        timeout = SANDBOX_DEFAULT_COMMAND_TIMEOUT

        try:
            result = await asyncio.wait_for(
                self._retry_operation(
                    sandbox.commands.run,
                    command,
                    timeout=timeout,
                    background=False,
                    envs=envs,
                ),
                timeout=timeout + 5,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Command execution timed out after {timeout}s")

        return str(result.stdout) + str(result.stderr)

    async def _execute_background_command(
        self,
        sandbox: AsyncSandbox,
        command: str,
        envs: dict[str, str],
    ) -> tuple[Any, list[str]]:
        initial_output: list[str] = []

        process = await self._retry_operation(
            sandbox.commands.run,
            command,
            background=True,
            timeout=None,
            on_stdout=BackgroundOutputCallback(initial_output, "stdout"),
            on_stderr=BackgroundOutputCallback(initial_output, "stderr"),
            envs=envs,
        )

        return process, initial_output

    async def clean_session_thinking_blocks(
        self, sandbox_id: str, session_id: str
    ) -> bool:
        session_file = f"/home/user/.claude/projects/-home-user/{session_id}.jsonl"
        temp_file = f"{session_file}.tmp"

        jq_filter = (
            'if .message.content and (.message.content | type) == "array" then '
            '.message.content |= [.[] | select((.type | IN("thinking", "redacted_thinking") | not) or ((.signature // "") | length) >= 10)] '
            "else . end"
        )

        try:
            cmd = (
                f"[ -f {shlex.quote(session_file)} ] && "
                f"jq -c '{jq_filter}' {shlex.quote(session_file)} > {shlex.quote(temp_file)} && "
                f"mv {shlex.quote(temp_file)} {shlex.quote(session_file)} && echo 'OK'"
            )
            result = await self.execute_command(sandbox_id, cmd)

            if "OK" in result:
                logger.info("Cleaned thinking blocks from session %s", session_id)
                return True

            return False
        except Exception as e:
            logger.error("Error cleaning session %s: %s", session_id, e)
            return False

    @staticmethod
    def normalize_path(file_path: str) -> str:
        base = "/home/user"
        path = PurePosixPath(file_path)

        if path.is_absolute() and str(path).startswith(base):
            return posixpath.normpath(str(path))
        elif path.is_absolute():
            return posixpath.normpath(f"{base}{path}")
        return posixpath.normpath(f"{base}/{path}")

    def _format_export_command(self, key: str, value: str) -> str:
        escaped_value = value.replace("'", "'\"'\"'")
        return f"export {key}='{escaped_value}'"

    async def _append_to_bashrc(
        self, sandbox: AsyncSandbox, export_command: str
    ) -> None:
        append_command = f'echo "{export_command}" >> ~/.bashrc'
        await self._retry_operation(
            sandbox.commands.run,
            append_command,
            timeout=5,
        )

    async def _source_bashrc(self, sandbox: AsyncSandbox) -> None:
        await self._retry_operation(
            sandbox.commands.run,
            "source ~/.bashrc",
            timeout=5,
        )

    async def _remove_from_bashrc(self, sandbox: AsyncSandbox, key: str) -> None:
        remove_command = f"sed -i '/^export {key}=/d' ~/.bashrc"
        await self._retry_operation(sandbox.commands.run, remove_command, timeout=5)

    async def _retry_operation(
        self, operation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        async for attempt in AsyncRetrying(**RETRY_CONFIG):
            with attempt:
                return await operation(*args, **kwargs)
