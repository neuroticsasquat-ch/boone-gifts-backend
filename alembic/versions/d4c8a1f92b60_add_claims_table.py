"""add claims table and move claim state off gifts

Revision ID: d4c8a1f92b60
Revises: b7e2d4f16c93
Create Date: 2026-09-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4c8a1f92b60'
down_revision: Union[str, Sequence[str], None] = 'b7e2d4f16c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    The claim moves off the gift and onto its own row (ADR 0003), so
    owner-blindness becomes a property of the schema rather than a rule every
    serializer has to remember.

    **Every existing claim is backfilled, carrying its purchase state.** Note
    the asymmetry with the family grants dropped in the revision before this
    one, and do not tidy it: a dropped grant is re-created by its owner in
    seconds, while a dropped claim silently invites two people to buy the same
    present. `occasion_id` and `amount_paid` start null — filing a claim under
    an occasion is NEU-1269, and nobody has recorded a spend yet.
    """
    # Stage the claims before touching `gifts`. Dropping a column under
    # `render_as_batch` recreates the whole table, and SQLite refuses that while
    # `claims.gift_id` points at it — so the data waits in a constraint-free
    # table until the gift row is its final shape.
    op.execute(
        """
        CREATE TABLE _claims_backfill AS
        SELECT id AS gift_id, claimed_by_id AS user_id,
               claimed_at, purchased_at
        FROM gifts
        WHERE claimed_by_id IS NOT NULL
        """
    )

    with op.batch_alter_table('gifts', schema=None) as batch_op:
        batch_op.drop_column('purchased_at')
        batch_op.drop_column('claimed_at')
        batch_op.drop_column('claimed_by_id')

    op.create_table(
        'claims',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gift_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=False),
        sa.Column('purchased_at', sa.DateTime(), nullable=True),
        sa.Column('amount_paid', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['gift_id'], ['gifts.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gift_id', name='uq_claims_gift'),
    )
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_claims_user_id'), ['user_id'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_claims_occasion_id'), ['occasion_id'], unique=False
        )

    # `gifts.claimed_at` was nullable and `claims.claimed_at` is not. Every row
    # the app wrote set the two together, so the fallback should never fire —
    # but a claim is not worth losing to a row that predates that.
    op.execute(
        """
        INSERT INTO claims (gift_id, user_id, occasion_id, claimed_at,
                            purchased_at, amount_paid)
        SELECT gift_id, user_id, NULL,
               COALESCE(claimed_at, CURRENT_TIMESTAMP), purchased_at, NULL
        FROM _claims_backfill
        """
    )
    op.execute("DROP TABLE _claims_backfill")


def downgrade() -> None:
    """Downgrade schema.

    The claim goes back onto the gift row with its purchase state intact.
    `amount_paid` and `occasion_id` have nowhere to go and are lost — there was
    no column for either before this revision.
    """
    # Columns first, foreign key last: adding a column is a plain ALTER, but
    # adding the FK recreates `gifts`, which SQLite refuses while `claims`
    # still points at it.
    with op.batch_alter_table('gifts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('claimed_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('claimed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('purchased_at', sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE gifts
        SET claimed_by_id = (SELECT user_id FROM claims WHERE claims.gift_id = gifts.id),
            claimed_at = (SELECT claimed_at FROM claims WHERE claims.gift_id = gifts.id),
            purchased_at = (SELECT purchased_at FROM claims WHERE claims.gift_id = gifts.id)
        WHERE EXISTS (SELECT 1 FROM claims WHERE claims.gift_id = gifts.id)
        """
    )

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_claims_occasion_id'))
        batch_op.drop_index(batch_op.f('ix_claims_user_id'))
    op.drop_table('claims')

    with op.batch_alter_table('gifts', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_gifts_claimed_by_id_users', 'users', ['claimed_by_id'], ['id']
        )
