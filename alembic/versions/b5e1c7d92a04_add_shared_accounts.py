"""add shared accounts: users.is_shared_account, account_people, lists.account_person_id

Revision ID: b5e1c7d92a04
Revises: a7c4e2b91f38
Create Date: 2026-09-07 19:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5e1c7d92a04'
down_revision: Union[str, Sequence[str], None] = 'a7c4e2b91f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Purely additive. No backfill: no existing account becomes a shared account,
    and `recipient_has_account = true` rows are left exactly as they are —
    NEU-1230 drops that column without converting them.
    """
    # Use ADD COLUMN directly (SQLite supports it natively for simple additions)
    # to avoid batch mode's drop/recreate, which trips PRAGMA foreign_keys=ON on
    # a table other tables reference. NOT NULL with a server_default, following
    # the `simple_mode` precedent in bb79d1d4eacb.
    op.add_column(
        'users',
        sa.Column(
            'is_shared_account', sa.Boolean(), server_default='0', nullable=False
        ),
    )

    op.create_table(
        'account_people',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_account_people_user_name'),
    )
    op.create_index(
        op.f('ix_account_people_user_id'), 'account_people', ['user_id'], unique=False
    )

    # Raw DDL, not op.add_column: alembic renders a column carrying a
    # ForeignKey as ADD COLUMN *plus* an ALTER TABLE ADD CONSTRAINT, which
    # SQLite has no support for (NotImplementedError, after the column is
    # already added). SQLite does accept an inline REFERENCES on ADD COLUMN as
    # long as the default is NULL, and that constraint is genuinely enforced
    # under PRAGMA foreign_keys=ON — which is what makes §4.4's "null the
    # labels before deleting the person" a real requirement rather than
    # bookkeeping. Batch mode is not an option here: it drops and recreates
    # `lists`, which gifts, list_shares, list_family_shares and occasion_items
    # all reference (see d8a3f1c05b64).
    op.execute(
        'ALTER TABLE lists ADD COLUMN account_person_id INTEGER '
        'REFERENCES account_people(id)'
    )
    op.create_index(
        op.f('ix_lists_account_person_id'), 'lists', ['account_person_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # DROP COLUMN directly rather than via batch mode, for the same reason the
    # upgrade adds directly: `lists` and `users` are both referenced by other
    # tables, so batch mode's drop/recreate trips PRAGMA foreign_keys=ON. SQLite
    # has supported DROP COLUMN natively since 3.35 (see d8a3f1c05b64).
    op.drop_index(op.f('ix_lists_account_person_id'), table_name='lists')
    op.drop_column('lists', 'account_person_id')
    op.drop_index(op.f('ix_account_people_user_id'), table_name='account_people')
    op.drop_table('account_people')
    op.drop_column('users', 'is_shared_account')
