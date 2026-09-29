"""Add api job support: task_instances.source/progress columns, meta_tasks.source, api_keys

Revision ID: 009
Revises: 008
Create Date: 2026-09-29

注意：`app/database.py::init_db()` 会在启动时执行 `Base.metadata.create_all`。
若服务先于本迁移启动，`api_keys` 表可能已被 create_all 建好（create_all 只补表、
不会给既有表补列），此时直接 `create_table` 会因表已存在而失败。因此这里对表/列
的创建做存在性判断，与 `_migrate_system_prompts` 的兼容思路一致，使迁移在
“先起服务”与“先跑迁移”两种顺序下都能成功。
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

_TASK_INSTANCE_COLUMNS = (
    ("source", sa.String(20), False, "web"),
    ("progress_stage", sa.String(30), True, None),
    ("progress_message", sa.String(200), True, None),
    ("progress_current", sa.Integer(), True, None),
    ("progress_total", sa.Integer(), True, None),
    ("heartbeat_at", sa.DateTime(), True, None),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _add_column_if_missing(table: str, column: str, type_: sa.types.TypeEngine, nullable: bool, server_default):
    existing = {c["name"] for c in _inspector().get_columns(table)}
    if column in existing:
        return
    op.add_column(table, sa.Column(column, type_, nullable=nullable, server_default=server_default))


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("009 迁移依赖存在性检查，仅支持在线执行（请勿使用 alembic --sql）")

    # 任务模板来源：api=开放接口内部使用的隐藏模板，不在网页列表中展示
    _add_column_if_missing("meta_tasks", "source", sa.String(20), False, "web")

    # 任务实例来源 + 检索进度上报（供开放接口轮询，避免调用方误判卡死）
    for column, type_, nullable, server_default in _TASK_INSTANCE_COLUMNS:
        _add_column_if_missing("task_instances", column, type_, nullable, server_default)

    inspector = _inspector()
    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("key_prefix", sa.String(16), nullable=False),
            sa.Column("key_hash", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_used_at", sa.DateTime()),
            sa.Column("expires_at", sa.DateTime()),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(datetime('now', 'localtime'))"),
            ),
        )
    index_names = {i["name"] for i in _inspector().get_indexes("api_keys")}
    if "ix_api_keys_key_prefix" not in index_names:
        op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("009 迁移依赖存在性检查，仅支持在线执行（请勿使用 alembic --sql）")

    inspector = _inspector()
    if inspector.has_table("api_keys"):
        index_names = {i["name"] for i in inspector.get_indexes("api_keys")}
        if "ix_api_keys_key_prefix" in index_names:
            op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
        op.drop_table("api_keys")

    existing = {c["name"] for c in _inspector().get_columns("task_instances")}
    for column, _type, _nullable, _default in _TASK_INSTANCE_COLUMNS:
        if column in existing:
            op.drop_column("task_instances", column)
    if "source" in {c["name"] for c in _inspector().get_columns("meta_tasks")}:
        op.drop_column("meta_tasks", "source")
