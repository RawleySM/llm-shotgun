"""Add LLM service models for token persistence and provider management

Revision ID: llm_service_v1
Revises: e33bb845793c
Create Date: 2025-01-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'llm_service_v1'
down_revision = 'e33bb845793c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create llm_requests table
    op.create_table('llm_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('models', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_llm_requests_id'), 'llm_requests', ['id'], unique=False)
    op.create_index(op.f('ix_llm_requests_request_id'), 'llm_requests', ['request_id'], unique=True)
    
    # Create llm_attempts table
    op.create_table('llm_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(), nullable=False),
        sa.Column('attempt_seq', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['llm_requests.request_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_llm_attempts_id'), 'llm_attempts', ['id'], unique=False)
    op.create_index(op.f('ix_llm_attempts_request_id'), 'llm_attempts', ['request_id'], unique=False)
    op.create_index('idx_request_attempt', 'llm_attempts', ['request_id', 'attempt_seq'], unique=False)
    
    # Create llm_token_log table
    op.create_table('llm_token_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(), nullable=False),
        sa.Column('attempt_seq', sa.Integer(), nullable=False),
        sa.Column('token_index', sa.Integer(), nullable=False),
        sa.Column('token_text', sa.Text(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['llm_requests.request_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_llm_token_log_id'), 'llm_token_log', ['id'], unique=False)
    op.create_index(op.f('ix_llm_token_log_request_id'), 'llm_token_log', ['request_id'], unique=False)
    op.create_index(op.f('ix_llm_token_log_ts'), 'llm_token_log', ['ts'], unique=False)
    op.create_index('idx_request_attempt_token', 'llm_token_log', ['request_id', 'attempt_seq', 'token_index'], unique=False)
    op.create_index('idx_ts', 'llm_token_log', ['ts'], unique=False)
    
    # Create provider_status table
    op.create_table('provider_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=True),
        sa.Column('last_failure', sa.DateTime(), nullable=True),
        sa.Column('last_success', sa.DateTime(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_provider_status_id'), 'provider_status', ['id'], unique=False)
    op.create_index(op.f('ix_provider_status_provider_name'), 'provider_status', ['provider_name'], unique=True)


def downgrade() -> None:
    # Drop indexes and tables in reverse order
    op.drop_index(op.f('ix_provider_status_provider_name'), table_name='provider_status')
    op.drop_index(op.f('ix_provider_status_id'), table_name='provider_status')
    op.drop_table('provider_status')
    
    op.drop_index('idx_ts', table_name='llm_token_log')
    op.drop_index('idx_request_attempt_token', table_name='llm_token_log')
    op.drop_index(op.f('ix_llm_token_log_ts'), table_name='llm_token_log')
    op.drop_index(op.f('ix_llm_token_log_request_id'), table_name='llm_token_log')
    op.drop_index(op.f('ix_llm_token_log_id'), table_name='llm_token_log')
    op.drop_table('llm_token_log')
    
    op.drop_index('idx_request_attempt', table_name='llm_attempts')
    op.drop_index(op.f('ix_llm_attempts_request_id'), table_name='llm_attempts')
    op.drop_index(op.f('ix_llm_attempts_id'), table_name='llm_attempts')
    op.drop_table('llm_attempts')
    
    op.drop_index(op.f('ix_llm_requests_request_id'), table_name='llm_requests')
    op.drop_index(op.f('ix_llm_requests_id'), table_name='llm_requests')
    op.drop_table('llm_requests') 