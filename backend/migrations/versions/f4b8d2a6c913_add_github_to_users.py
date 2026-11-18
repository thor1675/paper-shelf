"""add github account to users

GitHub の OAuth2 でログインできるよう、紐づけた GitHub アカウントの id と名前を持つ

Revision ID: f4b8d2a6c913
Revises: e2f7b4c91a36
Create Date: 2026-11-18 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f4b8d2a6c913'
down_revision: Union[str, Sequence[str], None] = 'e2f7b4c91a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('github_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('github_login', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True))
    op.create_unique_constraint('users_github_id_key', 'users', ['github_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('users_github_id_key', 'users', type_='unique')
    op.drop_column('users', 'github_login')
    op.drop_column('users', 'github_id')
