from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_create_providers"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("rating_avg", sa.Float, nullable=True),
        sa.Column("skills", sa.Text, nullable=True),
        sa.Column("price_band", sa.String(length=32), nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lon", sa.Float, nullable=True),
    )
    op.create_index("ix_providers_verified", "providers", ["verified"])
    op.create_index("ix_providers_rating", "providers", ["rating_avg"])

def downgrade() -> None:
    op.drop_index("ix_providers_rating", table_name="providers")
    op.drop_index("ix_providers_verified", table_name="providers")
    op.drop_table("providers")
