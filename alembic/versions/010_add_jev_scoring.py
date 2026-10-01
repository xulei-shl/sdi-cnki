"""Add JEV relevance scoring: jev_scores table, relevance_* on task_instances, config_type on llm_configs

Revision ID: 010
Revises: 009
Create Date: 2026-10-01

同 009：`init_db()` 会在启动时执行 `Base.metadata.create_all`，服务先于迁移启动时
新表可能已被建好、既有表不会被补列。故对建表与加列都做存在性判断，使迁移在
「先起服务」与「先跑迁移」两种顺序下都能成功。
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

_TASK_INSTANCE_COLUMNS = (
    ("relevance_status", sa.String(20), True, None),
    ("relevance_error", sa.Text(), True, None),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _add_column_if_missing(table: str, column: str, type_: sa.types.TypeEngine, nullable: bool, server_default):
    existing = {c["name"] for c in _inspector().get_columns(table)}
    if column in existing:
        return
    op.add_column(table, sa.Column(column, type_, nullable=nullable, server_default=server_default))


def _create_index_if_missing(name: str, table: str, column: str) -> None:
    """索引存在性判断必须重新取 inspector。

    alembic 在一次 upgrade 中缓存了 Inspector：若索引在同一次迁移的前段刚被创建
    （或列刚被 add_column），复用缓存的 get_indexes() 会拿到过期结果，导致索引
    被静默跳过——表结构缺索引不会报错，只在数据量上来后才显现为慢查询。
    """
    if not _inspector().has_table(table):
        return
    if name in {i["name"] for i in _inspector().get_indexes(table)}:
        return
    op.create_index(name, table, [column])


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("010 迁移依赖存在性检查，仅支持在线执行（请勿使用 alembic --sql）")

    # 配置类型：区分 OpenAI 兼容端点与 JEV(TypeSafe) 端点
    _add_column_if_missing("llm_configs", "config_type", sa.String(20), False, "llm")

    # 相关性评分状态（开放接口轮询需要 O(1) 读出，recovery 兜底需要落点）
    for column, type_, nullable, server_default in _TASK_INSTANCE_COLUMNS:
        _add_column_if_missing("task_instances", column, type_, nullable, server_default)

    inspector = _inspector()
    if not inspector.has_table("jev_scores"):
        op.create_table(
            "jev_scores",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "task_result_id",
                sa.Integer(),
                sa.ForeignKey("task_results.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "task_instance_id",
                sa.Integer(),
                sa.ForeignKey("task_instances.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("relevance_score", sa.Real()),
            sa.Column("relevance_level", sa.Integer()),
            sa.Column("noul_prob", sa.Real()),
            sa.Column("level_confidence", sa.Real()),
            sa.Column("latency_ms", sa.Integer()),
            sa.Column("raw_response", sa.Text()),
            sa.Column("error_message", sa.Text()),
            sa.Column("finished_at", sa.DateTime()),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(datetime('now', 'localtime'))"),
            ),
        )
        # 索引创建放在建表分支之外：即使 jev_scores 已由 create_all 建好，
    # 既有表上新加列的索引仍需补齐。
    for name, table, column in (
        ("ix_jev_scores_task_result_id", "jev_scores", "task_result_id"),
        ("ix_jev_scores_task_instance_id", "jev_scores", "task_instance_id"),
        ("ix_task_instances_relevance_status", "task_instances", "relevance_status"),
        ("ix_llm_configs_config_type", "llm_configs", "config_type"),
    ):
        _create_index_if_missing(name, table, column)


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("010 迁移依赖存在性检查，仅支持在线执行（请勿使用 alembic --sql）")

    inspector = _inspector()
    if inspector.has_table("jev_scores"):
        for name, table in (
            ("ix_jev_scores_task_instance_id", "jev_scores"),
            ("ix_jev_scores_task_result_id", "jev_scores"),
            ("ix_task_instances_relevance_status", "task_instances"),
            ("ix_llm_configs_config_type", "llm_configs"),
        ):
            if _inspector().has_table(table) and name in {
                i["name"] for i in _inspector().get_indexes(table)
            }:
                op.drop_index(name, table_name=table)
        op.drop_table("jev_scores")

    existing = {c["name"] for c in _inspector().get_columns("task_instances")}
    for column, _type, _nullable, _default in _TASK_INSTANCE_COLUMNS:
        if column in existing:
            op.drop_column("task_instances", column)
    if "config_type" in {c["name"] for c in _inspector().get_columns("llm_configs")}:
        op.drop_column("llm_configs", "config_type")