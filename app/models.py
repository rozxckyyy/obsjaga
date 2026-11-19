from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index,
    LargeBinary, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Role(StrEnum):
    STUDENT = "student"
    SPECIALIST = "specialist"
    ADMIN = "admin"


class Specialty(StrEnum):
    CARPENTER = "carpenter"
    ELECTRICIAN = "electrician"
    PLUMBER = "plumber"


class Status(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ROLE_NAMES = {
    Role.STUDENT: "Студент", Role.SPECIALIST: "Специалист", Role.ADMIN: "Администратор",
}
SPECIALTY_NAMES = {
    Specialty.CARPENTER: "Плотник",
    Specialty.ELECTRICIAN: "Электрик",
    Specialty.PLUMBER: "Сантехник",
}
STATUS_NAMES = {
    Status.NEW: "Новая",
    Status.IN_PROGRESS: "В работе",
    Status.COMPLETED: "Выполнена",
    Status.CANCELLED: "Отменена",
}


def enum_column(values: type[StrEnum], name: str) -> Enum:
    return Enum(
        values, name=name, values_callable=lambda members: [member.value for member in members], native_enum=False,
        create_constraint=True, validate_strings=True,
    )


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'specialist') = (specialty IS NOT NULL)",
            name="ck_users_specialty",
        ),
        CheckConstraint(
            "(role = 'student' AND dormitory IS NOT NULL AND room IS NOT NULL) OR "
            "(role <> 'student' AND dormitory IS NULL AND room IS NULL AND block IS NULL)",
            name="ck_users_address",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_column(Role, "ck_users_role"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    specialty: Mapped[Specialty | None] = mapped_column(enum_column(Specialty, "ck_users_specialty_value"))
    dormitory: Mapped[str | None] = mapped_column(String(120))
    room: Mapped[str | None] = mapped_column(String(32))
    block: Mapped[str | None] = mapped_column(String(32))


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "(status IN ('in_progress', 'completed')) = (assignee_id IS NOT NULL) "
            "AND (assignee_id IS NOT NULL) = (taken_at IS NOT NULL) "
            "AND (status = 'completed') = (completed_at IS NOT NULL)",
            name="ck_tickets_assignment",
        ),
        Index("ix_tickets_queue", "specialty", "created_at", "number", postgresql_where=text("status = 'new'")),
        Index("ix_tickets_author_created", "author_id", "created_at", "number"),
        Index("ix_tickets_assignee_created", "assignee_id", "created_at", "number"),
    )

    number: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    dormitory: Mapped[str] = mapped_column(String(120))
    room: Mapped[str] = mapped_column(String(32))
    block: Mapped[str | None] = mapped_column(String(32))
    specialty: Mapped[Specialty] = mapped_column(enum_column(Specialty, "ck_tickets_specialty"))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[Status] = mapped_column(enum_column(Status, "ck_tickets_status"), server_default=Status.NEW)
    revision: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User] = relationship(foreign_keys=[author_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])


class Preset(Base):
    __tablename__ = "presets"
    __table_args__ = (UniqueConstraint("specialty", "title", name="uq_presets_specialty_title"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    specialty: Mapped[Specialty] = mapped_column(enum_column(Specialty, "ck_presets_specialty"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("media_type IN ('image/jpeg', 'image/png')", name="ck_attachments_media_type"),
        CheckConstraint("octet_length(content) BETWEEN 1 AND 5242880", name="ck_attachments_size"),
    )

    ticket_number: Mapped[int] = mapped_column(ForeignKey("tickets.number", ondelete="CASCADE"), primary_key=True)
    media_type: Mapped[str] = mapped_column(String(10))
    content: Mapped[bytes] = mapped_column(LargeBinary)
