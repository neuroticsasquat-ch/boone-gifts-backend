"""drop users.simple_mode and family_invites.simple_mode

Revision ID: f1a6b3c80d27
Revises: c9d4e7a2f180
Create Date: 2026-09-08 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a6b3c80d27'
down_revision: Union[str, Sequence[str], None] = 'c9d4e7a2f180'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Simple mode is retired (ADR 0004). No backfill and nothing to preserve: the
    column recorded a preference, and the behaviour it drove — the auto-grant on
    list create and on family join — is deleted with it. *This revision* touches
    no grant: simple-mode owners keep the grants they already have and now manage
    them by hand like everyone else. (Project spec §12 drops every family grant
    when shares move to occasions; that is a later revision's doing, not this
    one's.)
    """
    # DROP COLUMN directly rather than via batch mode, following e2b7d4a91c53:
    # `users` is referenced by lists, family_members, list_shares, connections
    # and more, so batch mode's drop/recreate trips PRAGMA foreign_keys=ON.
    # SQLite has supported DROP COLUMN natively since 3.35.
    op.drop_column('users', 'simple_mode')
    op.drop_column('family_invites', 'simple_mode')


def downgrade() -> None:
    """Downgrade schema.

    Bare re-add at the original definitions (bb79d1d4eacb, 95844ef3641f), no
    backfill: every row comes back `False`, which under the pre-drop model reads
    as full mode. That is the safe direction — a downgraded database grants
    nothing automatically rather than re-sharing lists whose owners have since
    revoked those grants by hand.
    """
    op.add_column(
        'users',
        sa.Column('simple_mode', sa.Boolean(), server_default='0', nullable=False),
    )
    op.add_column(
        'family_invites',
        sa.Column('simple_mode', sa.Boolean(), server_default='0', nullable=False),
    )
