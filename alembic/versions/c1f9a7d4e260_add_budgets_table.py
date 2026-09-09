"""add budgets table

Revision ID: c1f9a7d4e260
Revises: d4c8a1f92b60
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f9a7d4e260'
down_revision: Union[str, Sequence[str], None] = 'd4c8a1f92b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    The last of the project's five revisions: what a user means to spend on one
    occasion or one folder. Nothing is backfilled — no budget has ever existed,
    and inventing one from what somebody has already spent would state a target
    the user never set.

    `occasion_id` and `folder_id` are mutually exclusive with exactly one set,
    and that rule is deliberately *not* a check constraint here. SQLite cannot
    add one without recreating the table under `render_as_batch`, and the
    service layer has to raise the 400 regardless — so a constraint would only
    duplicate the rule in the place it is hardest to change. The two unique
    constraints, which do carry their weight, coexist because a NULL never
    collides in a unique index.
    """
    op.create_table(
        'budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=True),
        sa.Column('folder_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'occasion_id', name='uq_budgets_user_occasion'),
        sa.UniqueConstraint('user_id', 'folder_id', name='uq_budgets_user_folder'),
    )
    with op.batch_alter_table('budgets', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_budgets_user_id'), ['user_id'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema.

    Every budget is lost — there is nowhere else in the schema to keep one.
    """
    with op.batch_alter_table('budgets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_budgets_user_id'))
    op.drop_table('budgets')
