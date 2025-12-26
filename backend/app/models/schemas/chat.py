from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, Field

from app.models.db_models import AttachmentType, MessageRole
from app.models.schemas.pagination import PaginatedResponse


class MessageAttachmentBase(BaseModel):
    file_url: str
    file_type: AttachmentType
    filename: str | None = None


class MessageAttachment(MessageAttachmentBase):
    id: UUID
    message_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=100000)
    chat_id: UUID | None = None
    model_id: str = Field(..., min_length=1, max_length=100)
    attached_files: list[UploadFile] | None = None
    permission_mode: Literal["plan", "ask", "auto"] = "auto"
    thinking_mode: str | None = Field(None, max_length=50)
    selected_prompt_name: str | None = Field(None, max_length=100)

    class Config:
        arbitrary_types_allowed = True


class MessageBase(BaseModel):
    content: str
    role: MessageRole


class Message(MessageBase):
    id: UUID
    chat_id: UUID
    created_at: datetime
    model_id: str | None = None
    attachments: list[MessageAttachment] = Field(default_factory=list)

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class ChatBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class ChatCreate(ChatBase):
    model_id: str = Field(..., min_length=1, max_length=100)


class ChatUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    pinned: bool | None = None


class Chat(ChatBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    sandbox_id: str | None = None
    context_token_usage: int | None = None
    pinned_at: datetime | None = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class ContextUsage(BaseModel):
    tokens_used: int
    context_window: int
    percentage: float


class PortPreviewLink(BaseModel):
    preview_url: str
    port: int


class PreviewLinksResponse(BaseModel):
    links: list[PortPreviewLink]


class ExecuteCommandResponse(BaseModel):
    output: str


class RestoreRequest(BaseModel):
    message_id: UUID


class PaginatedChats(PaginatedResponse[Chat]):
    pass


class PaginatedMessages(PaginatedResponse[Message]):
    pass


class ChatCompletionResponse(BaseModel):
    chat_id: UUID
    message_id: UUID


class EnhancePromptResponse(BaseModel):
    enhanced_prompt: str


class ChatStatusResponse(BaseModel):
    has_active_task: bool
    message_id: UUID | None = None
    last_event_id: str | None = None


class PermissionRespondResponse(BaseModel):
    success: bool
