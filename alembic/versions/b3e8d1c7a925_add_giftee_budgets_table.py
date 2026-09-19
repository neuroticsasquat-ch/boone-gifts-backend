"""add giftee_budgets table

Revision ID: b3e8d1c7a925
Revises: f6b2c9e41a58
Create Date: 2026-09-14 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e8d1c7a925'
down_revision: Union[str, Sequence[str], None] = 'f6b2c9e41a58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    What one user means to spend on one giftee within one occasion or folder
    (NEU-1326). Nothing is backfilled — no giftee budget has ever existed, and
    splitting an overall budget across people would state targets the user
    never set.

    The row carries both the giftee's three facts and the canonical key built
    from them (ADR 0006). Uniqueness needs the key: it is the one non-null
    column that identifies a giftee, and SQLite never collides two NULLs in a
    unique index, so `(owner_id, NULL, NULL)` would otherwise be storable
    twice. The foreign keys are real because "or the FK refuses" is how this
    repo catches a forgotten teardown.

    `occasion_id` and `folder_id` are mutually exclusive with exactly one set,
    and — as on `budgets` — that rule is the service's, not a check constraint.
    """
    op.create_table(
        'giftee_budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=True),
        sa.Column('folder_id', sa.Integer(), nullable=True),
        sa.Column('giftee_key', sa.String(length=300), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('account_person_id', sa.Integer(), nullable=True),
        sa.Column('recipient_name', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['account_person_id'], ['account_people.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'occasion_id', 'giftee_key',
            name='uq_giftee_budgets_user_occasion_key',
        ),
        sa.UniqueConstraint(
            'user_id', 'folder_id', 'giftee_key',
            name='uq_giftee_budgets_user_folder_key',
        ),
    )
    with op.batch_alter_table('giftee_budgets', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_giftee_budgets_user_id'), ['user_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_giftee_budgets_account_person_id'),
            ['account_person_id'],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema.

    Every giftee budget is lost — there is nowhere else in the schema to keep
    one. The overall `budgets` rows are untouched.
    """
    with op.batch_alter_table('giftee_budgets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_giftee_budgets_account_person_id'))
        batch_op.drop_index(batch_op.f('ix_giftee_budgets_user_id'))
    op.drop_table('giftee_budgets')
