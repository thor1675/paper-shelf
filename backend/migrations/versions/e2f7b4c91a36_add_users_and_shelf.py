"""add users and per-user shelf

ログインを付ける。論文の情報（papers）は全員で共有し、本棚・ステータス・タグ・メモ・読了日（shelf）と
新着のキーワード（watches）を人ごとにする。今ある論文とキーワードは user_id を NULL のまま shelf に移し、
最初に登録した人のものにする（auth.py の register）

Revision ID: e2f7b4c91a36
Revises: a7c3e9f1b2d4
Create Date: 2026-11-18 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e2f7b4c91a36'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f1b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False),
        sa.Column('slack_user_id', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('slack_user_id'),
    )
    op.create_table(
        'user_sessions',
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_hash'),
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table(
        'invites',
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column('used_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('code'),
    )
    op.create_table(
        'slack_link_codes',
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('code'),
    )

    # 本棚（人ごとのステータス・タグ・メモ・読了日）
    op.create_table(
        'shelf',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), server_default='', nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=16), server_default='unread', nullable=False),
        sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column('read_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
        sa.CheckConstraint("status IN ('unread', 'reading', 'read')", name='ck_shelf_status'),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'paper_id', name='uq_shelf_user_paper'),
    )
    op.create_index(op.f('ix_shelf_user_id'), 'shelf', ['user_id'], unique=False)
    op.create_index('ix_shelf_tags', 'shelf', ['tags'], unique=False, postgresql_using='gin')

    # 今ある論文の本棚の情報を移す（持ち主は最初に登録した人。それまでは NULL）
    op.execute(
        "INSERT INTO shelf (user_id, paper_id, tags, note, status, created_at, read_at) "
        "SELECT NULL, id, tags, note, status, created_at, read_at FROM papers ORDER BY id"
    )
    op.drop_index('ix_papers_tags', table_name='papers', postgresql_using='gin')
    op.drop_constraint('ck_papers_status', 'papers', type_='check')
    for column in ('tags', 'note', 'status', 'created_at', 'read_at'):
        op.drop_column('papers', column)

    # 新着のキーワードも人ごと（同じ語を別の人が登録できる）
    op.add_column('watches', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('watches_user_id_fkey', 'watches', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_watches_user_id'), 'watches', ['user_id'], unique=False)
    op.drop_constraint('watches_query_key', 'watches', type_='unique')
    op.create_unique_constraint('uq_watches_user_query', 'watches', ['user_id', 'query'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_watches_user_query', 'watches', type_='unique')
    # 人ごとに同じ語があると一意にできないので、古い方だけ残す
    op.execute("DELETE FROM watches a USING watches b WHERE a.query = b.query AND a.id > b.id")
    op.create_unique_constraint('watches_query_key', 'watches', ['query'])
    op.drop_index(op.f('ix_watches_user_id'), table_name='watches')
    op.drop_constraint('watches_user_id_fkey', 'watches', type_='foreignkey')
    op.drop_column('watches', 'user_id')

    op.add_column('papers', sa.Column('tags', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False))
    op.add_column('papers', sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), server_default='', nullable=False))
    op.add_column('papers', sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=16), server_default='unread', nullable=False))
    op.add_column('papers', sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column('papers', sa.Column('read_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
    # 本棚の情報は、いちばん小さい user_id（最初の人）のものを戻す
    op.execute(
        "UPDATE papers p SET tags = s.tags, note = s.note, status = s.status, created_at = s.created_at, read_at = s.read_at "
        "FROM (SELECT DISTINCT ON (paper_id) * FROM shelf ORDER BY paper_id, user_id NULLS FIRST) s WHERE s.paper_id = p.id"
    )
    op.create_check_constraint('ck_papers_status', 'papers', "status IN ('unread', 'reading', 'read')")
    op.create_index('ix_papers_tags', 'papers', ['tags'], unique=False, postgresql_using='gin')
    op.drop_index('ix_shelf_tags', table_name='shelf', postgresql_using='gin')
    op.drop_index(op.f('ix_shelf_user_id'), table_name='shelf')
    op.drop_table('shelf')
    op.drop_table('slack_link_codes')
    op.drop_table('invites')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_table('users')
