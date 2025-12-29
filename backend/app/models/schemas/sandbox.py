from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UpdateFileRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    content: str

    @field_validator("file_path")
    @classmethod
    def normalize_file_path(cls, v: str) -> str:
        if not v.startswith("/"):
            return f"/{v.lstrip('/')}"
        return v


class UpdateFileResponse(BaseModel):
    success: bool
    message: str


class FileMetadata(BaseModel):
    path: str
    type: str
    size: int
    modified: float
    is_binary: bool | None = None


class SandboxFilesMetadataResponse(BaseModel):
    files: list[FileMetadata]


class FileContentResponse(BaseModel):
    content: str
    path: str
    type: str
    is_binary: bool


class AddSecretRequest(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class UpdateSecretRequest(BaseModel):
    value: str = Field(..., min_length=1)


class UpdateIDEThemeRequest(BaseModel):
    theme: Literal["dark", "light"]


class IDEUrlResponse(BaseModel):
    url: str | None
