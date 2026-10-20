"""add status and gin indexes

Revision ID: c3e1a9d27b54
Revises: 8f4a83e99da9
Create Date: 2026-10-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c3e1a9d27b54'
down_revision: Union[str, Sequence[str], None] = '8f4a83e99da9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'papers',
        sa.Column(
            'status',
            sqlmodel.sql.sqltypes.AutoString(length=16),
            server_default='unread',
            nullable=False,
        ),
    )
    op.create_check_constraint(
        'ck_papers_status', 'papers', "status IN ('unread', 'reading', 'read')"
    )
    op.alter_column('papers', 'note', server_default='')
    # GIN インデックスは autogenerate では作られないので手で書く
    op.create_index('ix_papers_tags', 'papers', ['tags'], postgresql_using='gin')
    op.create_index('ix_papers_authors', 'papers', ['authors'], postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_papers_authors', table_name='papers')
    op.drop_index('ix_papers_tags', table_name='papers')
    op.alter_column('papers', 'note', server_default=None)
    op.drop_constraint('ck_papers_status', 'papers', type_='check')
    op.drop_column('papers', 'status')
