import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import GUID

from .enums import AttachmentType, MessageRole, MessageStreamStatus


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sandbox_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sandbox_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    context_token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User", back_populates="chats")
    messages = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_chats_user_id_id", "user_id", "id"),
        Index("idx_chats_user_id_sandbox_id", "user_id", "sandbox_id"),
        Index("idx_chats_user_id_deleted_at", "user_id", "deleted_at"),
        Index("idx_chats_user_id_updated_at_desc", "user_id", "updated_at"),
        Index("idx_chats_user_id_pinned_at", "user_id", "pinned_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        SQLAlchemyEnum(
            MessageRole,
            name="messagerole",
            values_callable=lambda obj: [entry.value for entry in obj],
        ),
        nullable=False,
    )
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=0.0
    )
    stream_status: Mapped[MessageStreamStatus] = mapped_column(
        SQLAlchemyEnum(
            MessageStreamStatus,
            name="messagestreamstatus",
            values_callable=lambda obj: [entry.value for entry in obj],
        ),
        nullable=False,
        default=MessageStreamStatus.COMPLETED,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    chat = relationship("Chat", back_populates="messages")
    attachments = relationship(
        "MessageAttachment", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_messages_chat_id_created_at", "chat_id", "created_at"),
        Index("idx_messages_role_created", "role", "created_at"),
        Index("idx_messages_stream_status", "stream_status"),
        Index("idx_messages_chat_id_deleted_at", "chat_id", "deleted_at"),
        Index("idx_messages_chat_id_role_deleted", "chat_id", "role", "deleted_at"),
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_url: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[AttachmentType] = mapped_column(
        SQLAlchemyEnum(
            AttachmentType,
            name="attachmenttype",
            values_callable=lambda obj: [entry.value for entry in obj],
        ),
        nullable=False,
        default=AttachmentType.IMAGE,
    )
    filename: Mapped[str | None] = mapped_column(String, nullable=True)

    message = relationship("Message", back_populates="attachments")
