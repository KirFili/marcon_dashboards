"""sku is_draft flag

Revision ID: b1f7a2c3d4e5
Revises: 2d4681a0ac41
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1f7a2c3d4e5'
down_revision: Union[str, Sequence[str], None] = '2d4681a0ac41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'skus',
        sa.Column('is_draft', sa.Boolean(), server_default=sa.text('false'),
                  nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('skus', 'is_draft')
