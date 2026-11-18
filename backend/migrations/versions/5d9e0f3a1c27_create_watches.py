"""create watches

Revision ID: 5d9e0f3a1c27
Revises: c3e1a9d27b54
Create Date: 2026-11-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5d9e0f3a1c27'
down_revision: Union[str, Sequence[str], None] = 'c3e1a9d27b54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 新着の通知に使う、arXiv の検索語の一覧
    op.create_table(
        'watches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('query', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        # 一度知らせた論文の ID（同じ論文を二度知らせないため）
        sa.Column('seen', sa.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column('notified_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('query'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('watches')
