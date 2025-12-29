from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class SandboxProviderType(str, Enum):
    E2B = "e2b"
    DOCKER = "docker"


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass
class FileMetadata:
    path: str
    type: str
    size: int
    modified: float
    is_binary: bool = False


@dataclass
class FileContent:
    path: str
    content: str
    type: str
    is_binary: bool


@dataclass
class PtySession:
    id: str
    pid: int | None
    rows: int
    cols: int


@dataclass
class PtySize:
    rows: int
    cols: int


@dataclass
class CheckpointInfo:
    message_id: str
    created_at: str


@dataclass
class PreviewLink:
    preview_url: str
    port: int


@dataclass
class SecretEntry:
    key: str
    value: str


@dataclass
class DockerConfig:
    image: str = "claudex-sandbox:latest"
    network: str = "claudex-sandbox-net"
    host: str | None = None
    preview_base_url: str = "http://localhost"
    user_home: str = "/home/user"
    openvscode_port: int = 8765
    sandbox_domain: str = ""
    traefik_network: str = ""


@dataclass
class SandboxContext:
    sandbox_id: str
    provider_type: SandboxProviderType
    connected: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


PtyDataCallbackType = Callable[[bytes], Coroutine[Any, Any, None]]
