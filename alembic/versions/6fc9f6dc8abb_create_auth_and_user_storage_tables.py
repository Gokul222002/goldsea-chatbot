"""create_auth_and_user_storage_tables

Revision ID: 6fc9f6dc8abb
Revises: 
Create Date: 2026-11-16 02:20:09.092031

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = '6fc9f6dc8abb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    # 1. users table
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. email_codes table
    if 'email_codes' not in existing_tables:
        op.create_table(
            'email_codes',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('code_hash', sa.String(length=255), nullable=False),
            sa.Column('purpose', sa.String(length=50), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_email_codes_user_id', 'email_codes', ['user_id'], unique=False)

    # 3. sessions table
    if 'sessions' not in existing_tables:
        op.create_table(
            'sessions',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('token_hash', sa.String(length=64), nullable=False),
            sa.Column('user_agent', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('ip_address', sa.String(length=45), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_active', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_sessions_user_id', 'sessions', ['user_id'], unique=False)
        op.create_index('ix_sessions_token_hash', 'sessions', ['token_hash'], unique=True)

    # 4. conversations table
    if 'conversations' not in existing_tables:
        op.create_table(
            'conversations',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('summary', sa.Text(), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_conversations_user_id', 'conversations', ['user_id'], unique=False)
    else:
        conv_cols = [c['name'] for c in inspector.get_columns('conversations')]
        if 'user_id' not in conv_cols:
            with op.batch_alter_table('conversations', schema=None) as batch_op:
                batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))
                batch_op.create_index(batch_op.f('ix_conversations_user_id'), ['user_id'], unique=False)
                batch_op.create_foreign_key('fk_conversations_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # 5. messages table
    if 'messages' not in existing_tables:
        op.create_table(
            'messages',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('conversation_id', sa.String(length=36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('role', sa.String(length=20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('sources', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('follow_up_chips', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('attachments', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False)
        op.create_index('ix_messages_user_id', 'messages', ['user_id'], unique=False)
    else:
        msg_cols = [c['name'] for c in inspector.get_columns('messages')]
        with op.batch_alter_table('messages', schema=None) as batch_op:
            if 'user_id' not in msg_cols:
                batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))
                batch_op.create_index(batch_op.f('ix_messages_user_id'), ['user_id'], unique=False)
                batch_op.create_foreign_key('fk_messages_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE')
            if 'attachments' not in msg_cols:
                batch_op.add_column(sa.Column('attachments', sa.Text(), server_default='[]'))

    # 6. memories table
    if 'memories' not in existing_tables:
        op.create_table(
            'memories',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('key', sa.String(length=100), nullable=False),
            sa.Column('value', sa.Text(), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=False, server_default='preference'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('user_id', 'key', name='uq_user_memory_key')
        )
        op.create_index('ix_memories_user_id', 'memories', ['user_id'], unique=False)
        op.create_index('ix_memories_key', 'memories', ['key'], unique=False)

    # 7. user_files table
    if 'user_files' not in existing_tables:
        op.create_table(
            'user_files',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('filename', sa.String(length=255), nullable=False),
            sa.Column('file_type', sa.String(length=50), nullable=False),
            sa.Column('mime_type', sa.String(length=100), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('extracted_text', sa.Text(), nullable=False, server_default=''),
            sa.Column('storage_path', sa.String(length=500), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_user_files_user_id', 'user_files', ['user_id'], unique=False)

def downgrade() -> None:
    op.drop_table('user_files')
    op.drop_table('memories')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('sessions')
    op.drop_table('email_codes')
    op.drop_table('users')
