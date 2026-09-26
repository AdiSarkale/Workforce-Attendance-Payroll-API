from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="ADMIN"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("employee_code", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("salary", sa.Numeric(12,2), nullable=False, server_default="0"),
        sa.UniqueConstraint("organization_id", "employee_code", name="uq_employee_org_code"))
    op.create_index("ix_employees_organization_id", "employees", ["organization_id"])
    op.create_table("sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"])
    op.create_table("employee_site_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("employee_id","site_id",name="uq_employee_site"))
    op.create_index("ix_employee_site_assignments_employee_id","employee_site_assignments",["employee_id"])
    op.create_index("ix_employee_site_assignments_site_id","employee_site_assignments",["site_id"])
    op.create_table("supervisor_site_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("user_id","site_id",name="uq_supervisor_site"))
    op.create_index("ix_supervisor_site_assignments_user_id","supervisor_site_assignments",["user_id"])
    op.create_index("ix_supervisor_site_assignments_site_id","supervisor_site_assignments",["site_id"])

def downgrade():
    op.drop_table("supervisor_site_assignments")
    op.drop_table("employee_site_assignments")
    op.drop_index("ix_sites_organization_id", table_name="sites")
    op.drop_table("sites")
    op.drop_index("ix_employees_organization_id", table_name="employees")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("organizations")
