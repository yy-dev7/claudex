from typing import Final

MAX_RESOURCE_NAME_LENGTH: Final[int] = 50
MIN_RESOURCE_NAME_LENGTH: Final[int] = 2
MAX_RESOURCES_PER_USER: Final[int] = 10
MAX_RESOURCE_SIZE_BYTES: Final[int] = 100 * 1024

REDIS_KEY_CHAT_TASK: Final[str] = "chat:{chat_id}:task"
REDIS_KEY_CHAT_STREAM: Final[str] = "chat:{chat_id}:stream"
REDIS_KEY_CHAT_REVOKED: Final[str] = "chat:{chat_id}:revoked"
REDIS_KEY_CHAT_CANCEL: Final[str] = "chat:{chat_id}:cancel"
REDIS_KEY_PERMISSION_REQUEST: Final[str] = "permission_request:{request_id}"
REDIS_KEY_PERMISSION_RESPONSE: Final[str] = "permission_response:{request_id}"
REDIS_KEY_USER_SETTINGS: Final[str] = "user_settings:{user_id}"
REDIS_KEY_MODELS_LIST: Final[str] = "models:list:{active_only}"

SANDBOX_AUTO_PAUSE_TIMEOUT: Final[int] = 3000
SANDBOX_DEFAULT_COMMAND_TIMEOUT: Final[int] = 120
MAX_CHECKPOINTS_PER_SANDBOX: Final[int] = 20
CHECKPOINT_BASE_DIR: Final[str] = "/home/user/.checkpoints"
PTY_OUTPUT_QUEUE_SIZE: Final[int] = 512
PTY_INPUT_QUEUE_SIZE: Final[int] = 1024

DOCKER_AVAILABLE_PORTS: Final[list[int]] = [
    3000,
    3001,
    5000,
    8000,
    8080,
    5173,
    4200,
    8888,
    4321,
    3030,
    5500,
    1234,
    4000,
]

SANDBOX_SYSTEM_VARIABLES: Final[list[str]] = [
    "SHELL",
    "PWD",
    "LOGNAME",
    "HOME",
    "USER",
    "SHLVL",
    "PS1",
    "PATH",
    "_",
    "NVM_DIR",
    "NODE_VERSION",
    "TERM",
]

SANDBOX_RESTORE_EXCLUDE_PATTERNS: Final[list[str]] = [
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

SANDBOX_EXCLUDED_PATHS: Final[list[str]] = [
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

SANDBOX_BINARY_EXTENSIONS: Final[set[str]] = {
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
