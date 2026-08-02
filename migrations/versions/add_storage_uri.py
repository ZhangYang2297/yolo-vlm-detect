"""add storage_uri to VideoSource

Revision ID: add_storage_uri
Revises: e701f2d627d3
Create Date: 2026-07-25 05:38:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "add_storage_uri"
down_revision = "e701f2d627d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("video_sources", sa.Column("storage_uri", sa.String(500), default="", comment="MinIO object URI"))


def downgrade():
    op.drop_column("video_sources", "storage_uri")