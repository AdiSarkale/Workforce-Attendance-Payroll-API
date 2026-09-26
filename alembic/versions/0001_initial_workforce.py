"""initial workforce schema

Revision ID: 0001_initial_workforce
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_workforce"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("organizations",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("name",sa.String(200),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table("users",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id")),
        sa.Column("email",sa.String(320),nullable=False),
        sa.Column("password_hash",sa.String(255),nullable=False),
        sa.Column("role",sa.String(50),nullable=False,server_default="ADMIN"),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("email"))
    op.create_index("ix_users_email","users",["email"],unique=True)
    op.create_table("employees",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("employee_code",sa.String(50),nullable=False),
        sa.Column("full_name",sa.String(200),nullable=False),
        sa.Column("email",sa.String(320)),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("salary",sa.Numeric(12,2),nullable=False,server_default="0"),
        sa.UniqueConstraint("organization_id","employee_code",name="uq_employee_org_code"))
    op.create_index("ix_employees_organization_id","employees",["organization_id"])
    op.create_table("sites",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("name",sa.String(200),nullable=False),
        sa.Column("qr_token_hash",sa.String(64),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_index("ix_sites_organization_id","sites",["organization_id"])
    op.create_table("employee_site_assignments",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),
        sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="CASCADE"),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("employee_id","site_id",name="uq_employee_site"))
    op.create_index("ix_employee_site_assignments_employee_id","employee_site_assignments",["employee_id"])
    op.create_index("ix_employee_site_assignments_site_id","employee_site_assignments",["site_id"])
    op.create_table("supervisor_site_assignments",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="CASCADE"),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("user_id","site_id",name="uq_supervisor_site"))
    op.create_index("ix_supervisor_site_assignments_user_id","supervisor_site_assignments",["user_id"])
    op.create_index("ix_supervisor_site_assignments_site_id","supervisor_site_assignments",["site_id"])
    op.create_table("attendance",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id",ondelete="CASCADE"),nullable=False),
        sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id"),nullable=False),
        sa.Column("work_date",sa.Date(),nullable=False),
        sa.Column("punch_in",sa.DateTime(timezone=True)),
        sa.Column("punch_out",sa.DateTime(timezone=True)),
        sa.Column("worked_minutes",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("overtime_minutes",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("status",sa.String(30),nullable=False,server_default="PRESENT"),
        sa.Column("approval_status",sa.String(30),nullable=False,server_default="PENDING"),
        sa.Column("approved_by",sa.Integer(),sa.ForeignKey("users.id")),
        sa.Column("approval_note",sa.Text()),
        sa.UniqueConstraint("employee_id","work_date",name="uq_employee_attendance_day"))
    op.create_index("ix_attendance_employee_id","attendance",["employee_id"])
    op.create_index("ix_attendance_site_id","attendance",["site_id"])
    op.create_index("ix_attendance_work_date","attendance",["work_date"])
    op.create_table("payroll_runs",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("year",sa.Integer(),nullable=False),
        sa.Column("month",sa.Integer(),nullable=False),
        sa.Column("status",sa.String(30),nullable=False,server_default="DRAFT"),
        sa.Column("created_by",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("finalized_at",sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id","year","month",name="uq_payroll_org_period"))
    op.create_index("ix_payroll_runs_organization_id","payroll_runs",["organization_id"])
    op.create_table("payroll_items",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("payroll_run_id",sa.Integer(),sa.ForeignKey("payroll_runs.id",ondelete="CASCADE"),nullable=False),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id"),nullable=False),
        sa.Column("gross_salary",sa.Numeric(12,2),nullable=False),
        sa.Column("deduction_amount",sa.Numeric(12,2),nullable=False,server_default="0"),
        sa.Column("overtime_amount",sa.Numeric(12,2),nullable=False,server_default="0"),
        sa.Column("final_payable",sa.Numeric(12,2),nullable=False),
        sa.Column("present_days",sa.Numeric(8,2),nullable=False,server_default="0"),
        sa.Column("leave_days",sa.Numeric(8,2),nullable=False,server_default="0"),
        sa.Column("overtime_minutes",sa.Integer(),nullable=False,server_default="0"),
        sa.UniqueConstraint("payroll_run_id","employee_id",name="uq_payroll_employee"))
    op.create_index("ix_payroll_items_payroll_run_id","payroll_items",["payroll_run_id"])
    op.create_index("ix_payroll_items_employee_id","payroll_items",["employee_id"])
    op.create_table("salary_slips",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("payroll_item_id",sa.Integer(),sa.ForeignKey("payroll_items.id",ondelete="CASCADE"),nullable=False),
        sa.Column("employee_id",sa.Integer(),sa.ForeignKey("employees.id"),nullable=False),
        sa.Column("year",sa.Integer(),nullable=False),
        sa.Column("month",sa.Integer(),nullable=False),
        sa.Column("slip_number",sa.String(80),nullable=False),
        sa.Column("generated_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("payroll_item_id"),
        sa.UniqueConstraint("slip_number"))
    op.create_index("ix_salary_slips_employee_id","salary_slips",["employee_id"])

def downgrade():
    op.drop_table("salary_slips")
    op.drop_table("payroll_items")
    op.drop_table("payroll_runs")
    op.drop_table("attendance")
    op.drop_table("supervisor_site_assignments")
    op.drop_table("employee_site_assignments")
    op.drop_table("sites")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("organizations")
