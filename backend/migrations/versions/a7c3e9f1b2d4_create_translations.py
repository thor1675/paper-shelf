"""create translations

Revision ID: a7c3e9f1b2d4
Revises: 8b41c6d2e0f5
Create Date: 2026-11-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f1b2d4'
down_revision: Union[str, Sequence[str], None] = '8b41c6d2e0f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 日本語で読む（訳した HTML を 1 本につき 1 行）
    op.create_table(
        'translations',
        sa.Column('arxiv_id', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column('done', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('source_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('html', sa.Text(), nullable=True),
        sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint('arxiv_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('translations')
