"""initial_schema

Revision ID: 1eb60ff2d910
Revises: 
Create Date: 2026-04-30 02:22:47.087140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2 as gis


# revision identifiers, used by Alembic.
revision: str = '1eb60ff2d910'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # Departments
    op.create_table(
        'departments_view',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('code', sa.String(20), nullable=False, unique=True),
        sa.Column('type', sa.String(20), nullable=True),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('head_employee_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Positions
    op.create_table(
        'positions_view',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('code', sa.String(20), nullable=True),
        sa.Column('department_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Employees
    op.create_table(
        'employees_view',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('personnel_number', sa.String(10), nullable=False, unique=True),
        sa.Column('full_name', sa.String(150), nullable=False),
        sa.Column('department_id', sa.UUID(), nullable=True),
        sa.Column('position_id', sa.UUID(), nullable=True),
        sa.Column('employment_type', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('hire_date', sa.Date(), nullable=True),
        sa.Column('termination_date', sa.Date(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.Column('source_event_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['department_id'], ['departments_view.id']),
        sa.ForeignKeyConstraint(['position_id'], ['positions_view.id'])
    )

    # EmployeeProfiles
    op.create_table(
        'employee_profiles',
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('last_name', sa.String(50), nullable=True),
        sa.Column('first_name', sa.String(50), nullable=True),
        sa.Column('patronymic', sa.String(50), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('preferred_locale', sa.String(10), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('employee_id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id'])
    )

    # Zones with PostGIS
    op.create_table(
        'zones',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('code', sa.String(20), nullable=False, unique=True),
        sa.Column('address', sa.String(255), nullable=True),
        sa.Column('geometry', gis.Geography(geometry_type='POLYGON', srid=4326), nullable=True),
        sa.Column('center_point', gis.Geography(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('access_level', sa.String(20), nullable=True),
        sa.Column('parent_zone_id', sa.UUID(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['parent_zone_id'], ['zones.id'])
    )
    op.create_index('zones_geometry_gist', 'zones', ['geometry'], postgresql_using='gist')

    # AccessPoints
    op.create_table(
        'access_points',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('zone_id', sa.UUID(), nullable=False),
        sa.Column('direction', sa.String(10), nullable=True),
        sa.Column('controller_address', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id'])
    )

    # AccessCards
    op.create_table(
        'access_cards',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('card_number', sa.String(20), nullable=False, unique=True),
        sa.Column('card_type', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('issued_at', sa.Date(), nullable=True),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('blocked_reason', sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id'])
    )

    # AccessRights
    op.create_table(
        'access_rights',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('zone_id', sa.UUID(), nullable=False),
        sa.Column('is_permitted', sa.Boolean(), default=True),
        sa.Column('granted_by_user_id', sa.UUID(), nullable=True),
        sa.Column('granted_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id']),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id']),
        sa.UniqueConstraint('employee_id', 'zone_id')
    )

    # ShiftAssignments
    op.create_table(
        'shift_assignments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('shift_template_id', sa.UUID(), nullable=True),
        sa.Column('shift_date', sa.Date(), nullable=False),
        sa.Column('planned_start', sa.DateTime(), nullable=False),
        sa.Column('planned_end', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('source_event_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id']),
        sa.UniqueConstraint('employee_id', 'shift_date')
    )

    # AttendanceRecords
    op.create_table(
        'attendance_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('shift_assignment_id', sa.UUID(), nullable=True),
        sa.Column('access_point_id', sa.UUID(), nullable=False),
        sa.Column('event_at', sa.DateTime(), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('source', sa.String(20), nullable=True),
        sa.Column('deny_reason', sa.String(200), nullable=True),
        sa.Column('credential_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id']),
        sa.ForeignKeyConstraint(['shift_assignment_id'], ['shift_assignments.id']),
        sa.ForeignKeyConstraint(['access_point_id'], ['access_points.id'])
    )
    op.create_index('attendance_records_employee_event_at', 'attendance_records', 
                   ['employee_id', 'event_at'], postgresql_using='btree')
    op.create_index('attendance_records_access_point_event_at', 'attendance_records',
                   ['access_point_id', 'event_at'], postgresql_using='btree')

    # Credentials
    op.create_table(
        'credentials',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('subject_type', sa.String(20), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=False),
        sa.Column('token_value', sa.String(64), nullable=False, unique=True),
        sa.Column('medium', sa.String(10), nullable=False),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('is_revoked', sa.Boolean(), default=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Timesheets
    op.create_table(
        'timesheets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('department_id', sa.UUID(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('generated_by_user_id', sa.UUID(), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('exported_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['department_id'], ['departments_view.id'])
    )

    # TimesheetEntries
    op.create_table(
        'timesheet_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('timesheet_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('time_kind', sa.String(20), nullable=False),
        sa.Column('regular_hours', sa.Numeric(4, 1), nullable=True),
        sa.Column('night_hours', sa.Numeric(4, 1), nullable=True),
        sa.Column('overtime_hours', sa.Numeric(4, 1), nullable=True),
        sa.Column('was_manually_adjusted', sa.Boolean(), default=False),
        sa.Column('adjustment_reason', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['timesheet_id'], ['timesheets.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id']),
        sa.UniqueConstraint('timesheet_id', 'employee_id', 'work_date')
    )

    # BookableResources
    op.create_table(
        'bookable_resources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('zone_id', sa.UUID(), nullable=False),
        sa.Column('floor', sa.Integer(), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id'])
    )

    # Bookings
    op.create_table(
        'bookings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('resource_id', sa.UUID(), nullable=False),
        sa.Column('start_at', sa.DateTime(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id']),
        sa.ForeignKeyConstraint(['resource_id'], ['bookable_resources.id'])
    )
    op.create_index('bookings_resource_time', 'bookings',
                   ['resource_id', 'start_at', 'end_at'])

    # GuestPasses
    op.create_table(
        'guest_passes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('invited_by_employee_id', sa.UUID(), nullable=False),
        sa.Column('guest_full_name', sa.String(150), nullable=False),
        sa.Column('guest_phone', sa.String(20), nullable=True),
        sa.Column('guest_company', sa.String(150), nullable=True),
        sa.Column('visit_purpose', sa.String(255), nullable=True),
        sa.Column('valid_from', sa.DateTime(), nullable=False),
        sa.Column('valid_until', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('approved_by_user_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['invited_by_employee_id'], ['employees_view.id'])
    )

    # GuestPassZones
    op.create_table(
        'guest_pass_zones',
        sa.Column('pass_id', sa.UUID(), nullable=False),
        sa.Column('zone_id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('pass_id', 'zone_id'),
        sa.ForeignKeyConstraint(['pass_id'], ['guest_passes.id']),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id'])
    )

    # Requests
    op.create_table(
        'requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('admin_comment', sa.String(500), nullable=True),
        sa.Column('processed_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id'])
    )

    # Notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('category', sa.String(30), nullable=True),
        sa.Column('is_read', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id'])
    )

    # DeviceTokens
    op.create_table(
        'device_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(10), nullable=False),
        sa.Column('fcm_token', sa.String(255), nullable=False, unique=True),
        sa.Column('app_version', sa.String(20), nullable=True),
        sa.Column('registered_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees_view.id'])
    )

    # OutboxMessages
    op.create_table(
        'outbox_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('correlation_id', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('outbox_messages_status_created', 'outbox_messages',
                   ['status', 'created_at'])

    # ProcessedInboundEvents
    op.create_table(
        'processed_inbound_events',
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('event_id')
    )

def downgrade() -> None:
    op.drop_table('processed_inbound_events')
    op.drop_table('outbox_messages')
    op.drop_table('device_tokens')
    op.drop_table('notifications')
    op.drop_table('requests')
    op.drop_table('guest_pass_zones')
    op.drop_table('guest_passes')
    op.drop_table('bookings')
    op.drop_table('bookable_resources')
    op.drop_table('timesheet_entries')
    op.drop_table('timesheets')
    op.drop_table('credentials')
    op.drop_table('attendance_records')
    op.drop_table('shift_assignments')
    op.drop_table('access_rights')
    op.drop_table('access_cards')
    op.drop_table('access_points')
    op.drop_table('zones')
    op.drop_table('employee_profiles')
    op.drop_table('employees_view')
    op.drop_table('positions_view')
    op.drop_table('departments_view')
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    op.execute("DROP EXTENSION IF EXISTS postgis")