import asyncio
import base64
import logging
import shlex
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable, TypeVar

import posixpath

from app.constants import (
    CHECKPOINT_BASE_DIR,
    MAX_CHECKPOINTS_PER_SANDBOX,
    SANDBOX_BINARY_EXTENSIONS,
    SANDBOX_EXCLUDED_PATHS,
    SANDBOX_RESTORE_EXCLUDE_PATTERNS,
    SANDBOX_SYSTEM_VARIABLES,
)
from app.services.sandbox_providers.types import (
    CheckpointInfo,
    CommandResult,
    FileContent,
    FileMetadata,
    PreviewLink,
    PtyDataCallbackType,
    PtySession,
    PtySize,
    SecretEntry,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

LISTENING_PORTS_COMMAND = "ss -tuln | grep LISTEN | awk '{print $5}' | sed 's/.*://g' | grep -E '^[0-9]+$' | sort -u"


class SandboxProvider(ABC):
    _pty_sessions: dict[str, dict[str, Any]]

    @staticmethod
    def normalize_path(file_path: str, base: str = "/home/user") -> str:
        path = PurePosixPath(file_path)

        if path.is_absolute() and str(path).startswith(base):
            return posixpath.normpath(str(path))
        elif path.is_absolute():
            return posixpath.normpath(f"{base}{path}")
        return posixpath.normpath(f"{base}/{path}")

    @staticmethod
    def format_export_command(key: str, value: str) -> str:
        escaped_value = value.replace("'", "'\"'\"'")
        return f"export {key}='{escaped_value}'"

    def _get_system_variables(self) -> list[str]:
        return SANDBOX_SYSTEM_VARIABLES

    @staticmethod
    def _is_binary_file(path: str) -> bool:
        return Path(path).suffix.lstrip(".").lower() in SANDBOX_BINARY_EXTENSIONS

    @staticmethod
    def _encode_file_content(path: str, content_bytes: bytes) -> tuple[str, bool]:
        is_binary = SandboxProvider._is_binary_file(path)
        if is_binary:
            content = base64.b64encode(content_bytes).decode("utf-8")
        else:
            content = content_bytes.decode("utf-8", errors="replace")
        return content, is_binary

    @staticmethod
    async def _execute_with_timeout(
        coro: Awaitable[T],
        timeout: int,
        error_msg: str | None = None,
    ) -> T:
        try:
            return await asyncio.wait_for(coro, timeout=timeout + 5)
        except asyncio.TimeoutError:
            raise TimeoutError(error_msg or f"Operation timed out after {timeout}s")

    @staticmethod
    def _parse_listening_ports(stdout: str) -> set[int]:
        return {int(p) for p in stdout.strip().splitlines() if p.isdigit()}

    def _build_preview_links(
        self,
        listening_ports: set[int],
        url_builder: Callable[[int], str],
        excluded_ports: set[int] | None = None,
    ) -> list[PreviewLink]:
        excluded = excluded_ports or set()
        preview_links: list[PreviewLink] = []
        for port in listening_ports:
            if port in excluded:
                continue
            preview_url = url_builder(port)
            preview_links.append(PreviewLink(preview_url=preview_url, port=port))
        return preview_links

    async def _get_latest_checkpoint_dir(self, sandbox_id: str) -> str | None:
        checkpoints = await self.list_checkpoints(sandbox_id)
        if not checkpoints:
            return None
        return f"{CHECKPOINT_BASE_DIR}/{checkpoints[0].message_id}"

    async def _cleanup_old_checkpoints(self, sandbox_id: str) -> int:
        checkpoints = await self.list_checkpoints(sandbox_id)

        if len(checkpoints) <= MAX_CHECKPOINTS_PER_SANDBOX:
            return 0

        to_delete = checkpoints[MAX_CHECKPOINTS_PER_SANDBOX:]
        deleted_count = 0

        for checkpoint in to_delete:
            checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{checkpoint.message_id}"
            await self.execute_command(
                sandbox_id, f"rm -rf {shlex.quote(checkpoint_dir)}"
            )
            deleted_count += 1

        return deleted_count

    def _get_pty_session(
        self, sandbox_id: str, session_id: str
    ) -> dict[str, Any] | None:
        return self._pty_sessions.get(sandbox_id, {}).get(session_id)

    def _register_pty_session(
        self, sandbox_id: str, session_id: str, session_data: dict[str, Any]
    ) -> None:
        if sandbox_id not in self._pty_sessions:
            self._pty_sessions[sandbox_id] = {}
        self._pty_sessions[sandbox_id][session_id] = session_data

    def _cleanup_pty_session_tracking(self, sandbox_id: str, session_id: str) -> None:
        try:
            del self._pty_sessions[sandbox_id][session_id]
            if not self._pty_sessions[sandbox_id]:
                del self._pty_sessions[sandbox_id]
        except Exception as e:
            logger.error("Error cleaning up PTY session %s: %s", session_id, e)

    @abstractmethod
    async def create_sandbox(self) -> str:
        pass

    @abstractmethod
    async def connect_sandbox(self, sandbox_id: str) -> bool:
        pass

    @abstractmethod
    async def delete_sandbox(self, sandbox_id: str) -> None:
        pass

    @abstractmethod
    async def is_running(self, sandbox_id: str) -> bool:
        pass

    @abstractmethod
    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        background: bool = False,
        envs: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        pass

    @abstractmethod
    async def write_file(
        self,
        sandbox_id: str,
        path: str,
        content: str | bytes,
    ) -> None:
        pass

    @abstractmethod
    async def read_file(
        self,
        sandbox_id: str,
        path: str,
    ) -> FileContent:
        pass

    async def list_files(
        self,
        sandbox_id: str,
        path: str = "/home/user",
        excluded_patterns: list[str] | None = None,
    ) -> list[FileMetadata]:
        patterns = excluded_patterns or SANDBOX_EXCLUDED_PATHS

        exclude_conditions = []
        for pattern in patterns:
            if pattern.startswith("*."):
                exclude_conditions.append(f"-not -name '{pattern}'")
            else:
                exclude_conditions.append(f"-not -path '{pattern}'")

        exclude_args = " ".join(exclude_conditions)
        find_command = f"find {path} {exclude_args} -printf '%p\t%y\t%s\t%T@\n'"

        result = await self.execute_command(sandbox_id, find_command, timeout=30)

        metadata_items = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 4:
                continue

            file_path, file_type, size, mtime = parts[0], parts[1], parts[2], parts[3]

            if not file_path or file_path == "/home/user" or file_path == "":
                continue

            if file_path.startswith("/home/user/"):
                file_path = file_path[11:]
            elif file_path.startswith("/home/user"):
                file_path = file_path[10:]

            if file_type == "f":
                is_binary = (
                    Path(file_path).suffix.lstrip(".").lower()
                    in SANDBOX_BINARY_EXTENSIONS
                )
                metadata_items.append(
                    FileMetadata(
                        path=file_path,
                        type="file",
                        is_binary=is_binary,
                        size=int(size) if size.isdigit() else 0,
                        modified=float(mtime)
                        if mtime.replace(".", "").isdigit()
                        else 0,
                    )
                )
            elif file_type == "d":
                metadata_items.append(
                    FileMetadata(
                        path=file_path,
                        type="directory",
                        size=0,
                        modified=float(mtime)
                        if mtime.replace(".", "").isdigit()
                        else 0,
                    )
                )

        return metadata_items

    @abstractmethod
    async def create_pty(
        self,
        sandbox_id: str,
        rows: int,
        cols: int,
        on_data: PtyDataCallbackType | None = None,
    ) -> PtySession:
        pass

    @abstractmethod
    async def send_pty_input(
        self,
        sandbox_id: str,
        pty_id: str,
        data: bytes,
    ) -> None:
        pass

    @abstractmethod
    async def resize_pty(
        self,
        sandbox_id: str,
        pty_id: str,
        size: PtySize,
    ) -> None:
        pass

    @abstractmethod
    async def kill_pty(
        self,
        sandbox_id: str,
        pty_id: str,
    ) -> None:
        pass

    @abstractmethod
    async def get_preview_links(self, sandbox_id: str) -> list[PreviewLink]:
        pass

    async def create_checkpoint(
        self,
        sandbox_id: str,
        checkpoint_id: str,
    ) -> str:
        # Creates a space-efficient incremental checkpoint using rsync hard links.
        # The --link-dest option creates hard links to unchanged files from the previous
        # checkpoint, meaning only modified files consume additional disk space.
        # For example, if checkpoint A has 100 files and checkpoint B only changes 2 files,
        # B will hard-link 98 files to A and only store 2 new copies.
        checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{checkpoint_id}"

        await self.execute_command(
            sandbox_id, f"mkdir -p {shlex.quote(CHECKPOINT_BASE_DIR)}"
        )

        prev_checkpoint = await self._get_latest_checkpoint_dir(sandbox_id)

        exclude_args = " ".join(
            f"--exclude={shlex.quote(pattern)}"
            for pattern in SANDBOX_RESTORE_EXCLUDE_PATTERNS
        )

        # Use --link-dest for incremental backup: unchanged files become hard links
        if prev_checkpoint:
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
            logger.error("Checkpoint creation failed for %s: %s", checkpoint_id, e)
            try:
                await self.execute_command(
                    sandbox_id, f"rm -rf {shlex.quote(checkpoint_dir)}"
                )
            except Exception:
                pass
            raise

        await self._cleanup_old_checkpoints(sandbox_id)
        return checkpoint_id

    async def restore_checkpoint(
        self,
        sandbox_id: str,
        checkpoint_id: str,
    ) -> bool:
        checkpoint_dir = f"{CHECKPOINT_BASE_DIR}/{checkpoint_id}"

        check_result = await self.execute_command(
            sandbox_id, f'[ -d {shlex.quote(checkpoint_dir)} ] && echo "1" || echo "0"'
        )

        if check_result.stdout.strip() != "1":
            raise FileNotFoundError(f"Checkpoint {checkpoint_id} not found")

        exclude_args = " ".join(
            f"--exclude={shlex.quote(pattern)}"
            for pattern in SANDBOX_RESTORE_EXCLUDE_PATTERNS
        )

        rsync_cmd = (
            f"rsync -a --delete "
            f"{exclude_args} "
            f"--stats "
            f"{shlex.quote(checkpoint_dir)}/ /home/user/"
        )

        await self.execute_command(sandbox_id, rsync_cmd)
        return True

    async def list_checkpoints(self, sandbox_id: str) -> list[CheckpointInfo]:
        check_result = await self.execute_command(
            sandbox_id,
            f'[ -d {shlex.quote(CHECKPOINT_BASE_DIR)} ] && echo "1" || echo "0"',
        )

        if check_result.stdout.strip() != "1":
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

        if not result.stdout.strip():
            return []

        checkpoints = []
        for line in result.stdout.strip().split("\n"):
            if "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) != 2:
                continue

            message_id, timestamp = parts
            try:
                ts = int(timestamp)
            except ValueError:
                continue
            checkpoints.append(
                CheckpointInfo(
                    message_id=message_id,
                    created_at=datetime.fromtimestamp(ts).isoformat(),
                )
            )

        checkpoints.sort(key=lambda x: x.created_at, reverse=True)
        return checkpoints

    async def get_secrets(self, sandbox_id: str) -> list[SecretEntry]:
        result = await self.execute_command(
            sandbox_id,
            "grep '^export' ~/.bashrc | sed 's/^export //g'",
            timeout=5,
        )

        env_lines = result.stdout.strip().split("\n")
        secrets = []
        system_vars = self._get_system_variables()

        for line in env_lines:
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip('"').strip("'")

                if key not in system_vars:
                    secrets.append(SecretEntry(key=key, value=value))

        return secrets

    async def add_secret(
        self,
        sandbox_id: str,
        key: str,
        value: str,
    ) -> None:
        export_command = self.format_export_command(key, value)
        await self.execute_command(
            sandbox_id, f'echo "{export_command}" >> ~/.bashrc && source ~/.bashrc'
        )

    async def delete_secret(
        self,
        sandbox_id: str,
        key: str,
    ) -> None:
        escaped_key = key.replace(".", r"\.").replace("*", r"\*")
        await self.execute_command(
            sandbox_id, f"sed -i '/^export {escaped_key}=/d' ~/.bashrc"
        )

    async def cleanup(self) -> None:
        for sandbox_id in list(self._pty_sessions.keys()):
            for session_id in list(self._pty_sessions[sandbox_id].keys()):
                try:
                    await self.kill_pty(sandbox_id, session_id)
                except Exception as e:
                    logger.warning(
                        "Failed to cleanup PTY session %s for sandbox %s: %s",
                        session_id,
                        sandbox_id,
                        e,
                    )

    @abstractmethod
    async def get_ide_url(self, sandbox_id: str) -> str | None:
        pass

    async def __aenter__(self) -> "SandboxProvider":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        await self.cleanup()
        return False
