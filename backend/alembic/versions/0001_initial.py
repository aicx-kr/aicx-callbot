"""initial schema — 12 테이블 일괄 생성.

기존 _migrate_sqlite_add_columns() 의 누락 7컬럼도 포함:
- bots.branches, bots.voice_rules
- bots.external_kb_enabled, bots.external_kb_inquiry_types
- call_sessions.dynamic_vars
- callbot_agents.global_rules
- skills.allowed_tool_names

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. tenants ────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("name", name="uq_tenants_name"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    # 2. bots ───────────────────────────────────────────────
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("persona", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("greeting", sa.String(500), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("voice", sa.String(64), nullable=True),
        sa.Column("llm_model", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("agent_type", sa.String(16), nullable=True),
        sa.Column("graph", sa.JSON(), nullable=True),
        sa.Column("env_vars", sa.JSON(), nullable=True),
        sa.Column("branches", sa.JSON(), nullable=True),
        sa.Column("voice_rules", sa.Text(), nullable=True),
        sa.Column("external_kb_enabled", sa.Boolean(), nullable=True),
        sa.Column("external_kb_inquiry_types", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_bots_tenant_id"),
    )
    op.create_index("ix_bots_tenant_id", "bots", ["tenant_id"])

    # 3. callbot_agents ─────────────────────────────────────
    op.create_table(
        "callbot_agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("voice", sa.String(64), nullable=True),
        sa.Column("greeting", sa.String(500), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("llm_model", sa.String(64), nullable=True),
        sa.Column("pronunciation_dict", sa.JSON(), nullable=True),
        sa.Column("dtmf_map", sa.JSON(), nullable=True),
        sa.Column("global_rules", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_callbot_agents_tenant_id"),
    )
    op.create_index("ix_callbot_agents_tenant_id", "callbot_agents", ["tenant_id"])

    # 4. callbot_memberships ────────────────────────────────
    op.create_table(
        "callbot_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("callbot_id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(8), nullable=True),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.Column("branch_trigger", sa.Text(), nullable=True),
        sa.Column("voice_override", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["callbot_id"], ["callbot_agents.id"], name="fk_callbot_memberships_callbot_id"),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_callbot_memberships_bot_id"),
    )
    op.create_index("ix_callbot_memberships_callbot_id", "callbot_memberships", ["callbot_id"])
    op.create_index("ix_callbot_memberships_bot_id", "callbot_memberships", ["bot_id"])

    # 5. skills ─────────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("graph", sa.JSON(), nullable=True),
        sa.Column("is_frontdoor", sa.Boolean(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.Column("allowed_tool_names", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_skills_bot_id"),
    )
    op.create_index("ix_skills_bot_id", "skills", ["bot_id"])

    # 6. knowledge ──────────────────────────────────────────
    op.create_table(
        "knowledge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_knowledge_bot_id"),
    )
    op.create_index("ix_knowledge_bot_id", "knowledge", ["bot_id"])

    # 7. mcp_servers ────────────────────────────────────────
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("mcp_tenant_id", sa.String(64), nullable=True),
        sa.Column("auth_header", sa.String(500), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=True),
        sa.Column("discovered_tools", sa.JSON(), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_mcp_servers_bot_id"),
    )
    op.create_index("ix_mcp_servers_bot_id", "mcp_servers", ["bot_id"])

    # 8. tools ──────────────────────────────────────────────
    op.create_table(
        "tools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(16), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=True),
        sa.Column("auto_call_on", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_tools_bot_id"),
    )
    op.create_index("ix_tools_bot_id", "tools", ["bot_id"])

    # 9. call_sessions ──────────────────────────────────────
    op.create_table(
        "call_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("end_reason", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("extracted", sa.JSON(), nullable=True),
        sa.Column("analysis_status", sa.String(16), nullable=True),
        sa.Column("dynamic_vars", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_call_sessions_bot_id"),
        sa.UniqueConstraint("room_id", name="uq_call_sessions_room_id"),
    )
    op.create_index("ix_call_sessions_bot_id", "call_sessions", ["bot_id"])

    # 10. transcripts ───────────────────────────────────────
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["call_sessions.id"], name="fk_transcripts_session_id"),
    )
    op.create_index("ix_transcripts_session_id", "transcripts", ["session_id"])

    # 11. tool_invocations ──────────────────────────────────
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["call_sessions.id"], name="fk_tool_invocations_session_id"),
    )
    op.create_index("ix_tool_invocations_session_id", "tool_invocations", ["session_id"])

    # 12. traces ────────────────────────────────────────────
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("t_start_ms", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["call_sessions.id"], name="fk_traces_session_id"),
        sa.ForeignKeyConstraint(["parent_id"], ["traces.id"], name="fk_traces_parent_id"),
    )
    op.create_index("ix_traces_session_id", "traces", ["session_id"])
    op.create_index("ix_traces_parent_id", "traces", ["parent_id"])


def downgrade() -> None:
    # 역순으로 drop (FK 의존성)
    op.drop_index("ix_traces_parent_id", table_name="traces")
    op.drop_index("ix_traces_session_id", table_name="traces")
    op.drop_table("traces")

    op.drop_index("ix_tool_invocations_session_id", table_name="tool_invocations")
    op.drop_table("tool_invocations")

    op.drop_index("ix_transcripts_session_id", table_name="transcripts")
    op.drop_table("transcripts")

    op.drop_index("ix_call_sessions_bot_id", table_name="call_sessions")
    op.drop_table("call_sessions")

    op.drop_index("ix_tools_bot_id", table_name="tools")
    op.drop_table("tools")

    op.drop_index("ix_mcp_servers_bot_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")

    op.drop_index("ix_knowledge_bot_id", table_name="knowledge")
    op.drop_table("knowledge")

    op.drop_index("ix_skills_bot_id", table_name="skills")
    op.drop_table("skills")

    op.drop_index("ix_callbot_memberships_bot_id", table_name="callbot_memberships")
    op.drop_index("ix_callbot_memberships_callbot_id", table_name="callbot_memberships")
    op.drop_table("callbot_memberships")

    op.drop_index("ix_callbot_agents_tenant_id", table_name="callbot_agents")
    op.drop_table("callbot_agents")

    op.drop_index("ix_bots_tenant_id", table_name="bots")
    op.drop_table("bots")

    op.drop_table("tenants")
