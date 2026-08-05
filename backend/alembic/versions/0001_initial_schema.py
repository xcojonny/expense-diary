"""Ausgangsschema.

Autogeneriert aus den Modellen. Beträge sind Integer-Cent, Mengen Tausendstel
(ADR-003); Primärschlüssel sind Integer (ADR-008). `batch_alter_table` kommt
von `render_as_batch=True` — SQLite kennt kein ALTER COLUMN (ADR-001).

Revision ID: 0001_initial
Revises: -
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0001_initial'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_tokens_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_tokens_token_hash'), ['token_hash'], unique=True)

    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_food', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('parent_id', 'name', name='uq_categories_parent_name')
    )
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_categories_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_categories_parent_id'), ['parent_id'], unique=False)

    op.create_table('receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('store_name', sa.String(length=160), nullable=True),
    sa.Column('purchased_at', sa.DateTime(), nullable=True),
    sa.Column('total_cents', sa.Integer(), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('file_path', sa.String(length=300), nullable=True),
    sa.Column('file_media_type', sa.String(length=80), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('raw_text', sa.Text(), nullable=True),
    sa.Column('confidence', sa.String(length=10), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('uploaded','processing','done','needs_review','failed')", name='ck_receipts_status'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_receipts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_purchased_at'), ['purchased_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_status'), ['status'], unique=False)

    op.create_table('items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('normalized_name', sa.String(length=240), nullable=False),
    sa.Column('display_name', sa.String(length=240), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_items_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_items_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_items_normalized_name'), ['normalized_name'], unique=True)

    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('receipt_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('run_after', sa.DateTime(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('queued','running','done','failed')", name='ck_jobs_status'),
    sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_receipt_id'), ['receipt_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_run_after'), ['run_after'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)

    op.create_table('line_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('receipt_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('normalized_name', sa.String(length=240), nullable=False),
    sa.Column('quantity_milli', sa.Integer(), nullable=True),
    sa.Column('unit', sa.String(length=16), nullable=True),
    sa.Column('unit_price_cents', sa.Integer(), nullable=True),
    sa.Column('total_price_cents', sa.Integer(), nullable=False),
    sa.Column('vat_class', sa.String(length=4), nullable=True),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("kind IN ('product','deposit','discount')", name='ck_line_items_kind'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('line_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_line_items_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_line_items_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_line_items_item_id'), ['item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_line_items_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_line_items_normalized_name'), ['normalized_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_line_items_receipt_id'), ['receipt_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('line_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_line_items_receipt_id'))
        batch_op.drop_index(batch_op.f('ix_line_items_normalized_name'))
        batch_op.drop_index(batch_op.f('ix_line_items_kind'))
        batch_op.drop_index(batch_op.f('ix_line_items_item_id'))
        batch_op.drop_index(batch_op.f('ix_line_items_created_at'))
        batch_op.drop_index(batch_op.f('ix_line_items_category_id'))

    op.drop_table('line_items')
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_status'))
        batch_op.drop_index(batch_op.f('ix_jobs_run_after'))
        batch_op.drop_index(batch_op.f('ix_jobs_receipt_id'))
        batch_op.drop_index(batch_op.f('ix_jobs_created_at'))

    op.drop_table('jobs')
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_items_normalized_name'))
        batch_op.drop_index(batch_op.f('ix_items_created_at'))
        batch_op.drop_index(batch_op.f('ix_items_category_id'))

    op.drop_table('items')
    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_receipts_status'))
        batch_op.drop_index(batch_op.f('ix_receipts_purchased_at'))
        batch_op.drop_index(batch_op.f('ix_receipts_created_at'))

    op.drop_table('receipts')
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_categories_parent_id'))
        batch_op.drop_index(batch_op.f('ix_categories_created_at'))

    op.drop_table('categories')
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_api_tokens_created_at'))

    op.drop_table('api_tokens')
