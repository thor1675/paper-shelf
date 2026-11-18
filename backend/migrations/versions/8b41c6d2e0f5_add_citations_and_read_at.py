"""add citations and read_at

Revision ID: 8b41c6d2e0f5
Revises: 5d9e0f3a1c27
Create Date: 2026-11-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8b41c6d2e0f5'
down_revision: Union[str, Sequence[str], None] = '5d9e0f3a1c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 読書の記録
    op.add_column('papers', sa.Column('read_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
    # OpenAlex から取った引用の情報
    op.add_column('papers', sa.Column('openalex_id', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True))
    op.add_column('papers', sa.Column('citation_count', sa.Integer(), nullable=True))
    op.add_column('papers', sa.Column('reference_ids', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False))
    op.add_column('papers', sa.Column('scholar_synced_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
    op.create_index(op.f('ix_papers_openalex_id'), 'papers', ['openalex_id'], unique=False)
    op.create_table(
        'scholar_cache',
        sa.Column('key', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fetched_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('scholar_cache')
    op.drop_index(op.f('ix_papers_openalex_id'), table_name='papers')
    op.drop_column('papers', 'scholar_synced_at')
    op.drop_column('papers', 'reference_ids')
    op.drop_column('papers', 'citation_count')
    op.drop_column('papers', 'openalex_id')
    op.drop_column('papers', 'read_at')
