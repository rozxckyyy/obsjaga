"""Create users, tickets, presets and photo attachments."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("specialty", sa.Enum(
            "carpenter", "electrician", "plumber",
            name="ck_presets_specialty", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("specialty", "title", name="uq_presets_specialty_title"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(40), unique=True, nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum(
            "student", "specialist", "admin",
            name="ck_users_role", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("specialty", sa.Enum(
            "carpenter", "electrician", "plumber",
            name="ck_users_specialty_value", native_enum=False, create_constraint=True,
        )),
        sa.Column("dormitory", sa.String(120)),
        sa.Column("room", sa.String(32)),
        sa.Column("block", sa.String(32)),
        sa.CheckConstraint(
            "(role = 'specialist') = (specialty IS NOT NULL)", name="ck_users_specialty",
        ),
        sa.CheckConstraint(
            "(role = 'student' AND dormitory IS NOT NULL AND room IS NOT NULL) OR "
            "(role <> 'student' AND dormitory IS NULL AND room IS NULL AND block IS NULL)",
            name="ck_users_address",
        ),
    )
    op.create_table(
        "tickets",
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("dormitory", sa.String(120), nullable=False),
        sa.Column("room", sa.String(32), nullable=False),
        sa.Column("block", sa.String(32)),
        sa.Column("specialty", sa.Enum(
            "carpenter", "electrician", "plumber",
            name="ck_tickets_specialty", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum(
            "new", "in_progress", "completed", "cancelled",
            name="ck_tickets_status", native_enum=False, create_constraint=True,
        ), server_default="new", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(status IN ('in_progress', 'completed')) = (assignee_id IS NOT NULL) "
            "AND (assignee_id IS NOT NULL) = (taken_at IS NOT NULL) "
            "AND (status = 'completed') = (completed_at IS NOT NULL)",
            name="ck_tickets_assignment",
        ),
    )
    op.create_index("ix_tickets_assignee_created", "tickets", ["assignee_id", "created_at", "number"])
    op.create_index("ix_tickets_author_created", "tickets", ["author_id", "created_at", "number"])
    op.create_index(
        "ix_tickets_queue", "tickets", ["specialty", "created_at", "number"],
        postgresql_where=sa.text("status = 'new'"),
    )
    op.create_table(
        "attachments",
        sa.Column("ticket_number", sa.Integer(), sa.ForeignKey("tickets.number", ondelete="CASCADE"), primary_key=True),
        sa.Column("media_type", sa.String(10), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("media_type IN ('image/jpeg', 'image/png')", name="ck_attachments_media_type"),
        sa.CheckConstraint("octet_length(content) BETWEEN 1 AND 5242880", name="ck_attachments_size"),
    )


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_table("tickets")
    op.drop_table("users")
    op.drop_table("presets")
