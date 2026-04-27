"""Smart reminders: warned_2h, warned_exact for tasks; deadline + warn flags for task_steps

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-04-27 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tasks jadvaliga yangi flaglar
    op.add_column('tasks', sa.Column('warned_2h',    sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('tasks', sa.Column('warned_exact', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # TaskStep jadvaliga deadline + flaglar
    op.add_column('task_steps', sa.Column('deadline',           sa.DateTime(timezone=True), nullable=True))
    op.add_column('task_steps', sa.Column('step_warned_morning',sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('task_steps', sa.Column('step_warned_3h',     sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('task_steps', sa.Column('step_warned_2h',     sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('task_steps', sa.Column('step_warned_1h',     sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('task_steps', sa.Column('step_warned_exact',  sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('tasks', 'warned_2h')
    op.drop_column('tasks', 'warned_exact')
    op.drop_column('task_steps', 'deadline')
    op.drop_column('task_steps', 'step_warned_morning')
    op.drop_column('task_steps', 'step_warned_3h')
    op.drop_column('task_steps', 'step_warned_2h')
    op.drop_column('task_steps', 'step_warned_1h')
    op.drop_column('task_steps', 'step_warned_exact')
