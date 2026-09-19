import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class SessionStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


def _enum_values(enum_class: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_class]


class TherapySession(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "therapy_sessions"
    __table_args__ = (Index("therapy_sessions_user_id_idx", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # Points at the YAML script library, not a DB row.
    script_id: Mapped[str] = mapped_column(String(100))
    current_section: Mapped[str] = mapped_column(String(100))
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", values_callable=_enum_values),
        server_default=text("'active'"),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("messages_session_id_idx", "session_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("therapy_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=_enum_values)
    )
    content: Mapped[str] = mapped_column(Text)
    section_at_time: Mapped[str] = mapped_column(String(100))


class SectionTransition(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "section_transitions"
    __table_args__ = (Index("section_transitions_session_id_idx", "session_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("therapy_sessions.id", ondelete="CASCADE")
    )
    # Null for the first transition into section 1.
    from_section: Mapped[str | None] = mapped_column(String(100))
    to_section: Mapped[str] = mapped_column(String(100))
    # The assess/dispatch "thought", not shown to the patient.
    reasoning: Mapped[str | None] = mapped_column(Text)
