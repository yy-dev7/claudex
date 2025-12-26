from typing import Literal, TypedDict


class BaseResourceDict(TypedDict, total=False):
    name: str
    description: str
    content: str
    enabled: bool


class CustomAgentDict(BaseResourceDict, total=False):
    model: Literal["sonnet", "opus", "haiku", "inherit"]
    allowed_tools: list[str] | None


class CustomMcpDict(TypedDict, total=False):
    name: str
    description: str
    command_type: Literal["npx", "bunx", "uvx", "http"]
    package: str | None
    url: str | None
    env_vars: dict[str, str] | None
    args: list[str] | None
    enabled: bool


class CustomEnvVarDict(TypedDict, total=False):
    key: str
    value: str


class CustomSkillDict(TypedDict, total=False):
    name: str
    description: str
    enabled: bool
    size_bytes: int
    file_count: int


class CustomSlashCommandDict(BaseResourceDict, total=False):
    argument_hint: str | None
    allowed_tools: list[str] | None
    model: (
        Literal[
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-haiku-4-5-20251001",
        ]
        | None
    )


class CustomPromptDict(TypedDict, total=False):
    name: str
    content: str


class MessageAttachmentDict(TypedDict, total=False):
    file_url: str
    file_path: str | None
    file_type: str
    filename: str | None


class ChatCompletionResult(TypedDict):
    task_id: str
    message_id: str
    chat_id: str
    status: str


class FileMetadataDict(TypedDict, total=False):
    path: str
    type: str
    size: int
    modified: float
    is_binary: bool | None


class YamlFrontmatterResult(TypedDict):
    metadata: "YamlMetadata"
    markdown_content: str


class YamlMetadata(TypedDict, total=False):
    name: str
    description: str
    model: str | None
    allowed_tools: list[str] | None
    argument_hint: str | None


class ParsedResourceResult(TypedDict):
    metadata: YamlMetadata
    content: str
    markdown_content: str


class EnabledResourceInfo(TypedDict):
    name: str
    path: str


ExceptionDetails = dict[str, str]


type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
)
type JSONDict = dict[str, JSONValue]
type JSONList = list[JSONValue]
