"""Initial PostgreSQL schema for FamilienPlan.

Revision ID: 0001
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA = r"""
CREATE TYPE role AS ENUM ('VIEWER','EDITOR','ADMIN');
CREATE TYPE child_permission AS ENUM ('VIEW','EDIT');
CREATE TYPE plan_status AS ENUM ('DRAFT','PROPOSED','CHANGE_PROPOSED','CONFIRMED','REJECTED','CANCELLED');
CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, display_name VARCHAR(160) NOT NULL, first_name VARCHAR(100), last_name VARCHAR(100), email VARCHAR(320) NOT NULL UNIQUE, phone VARCHAR(40), password_hash VARCHAR(512) NOT NULL, role role NOT NULL, language VARCHAR(10) NOT NULL DEFAULT 'de', timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Berlin', is_active BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX ix_users_username ON users(username); CREATE INDEX ix_users_email ON users(email);
CREATE TABLE sessions (id SERIAL PRIMARY KEY, token_hash VARCHAR(64) NOT NULL UNIQUE, csrf_token VARCHAR(128) NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX ix_sessions_token_hash ON sessions(token_hash); CREATE INDEX ix_sessions_user_id ON sessions(user_id); CREATE INDEX ix_sessions_expires_at ON sessions(expires_at);
CREATE TABLE invitations (id SERIAL PRIMARY KEY, email VARCHAR(320) NOT NULL, role role NOT NULL, display_name VARCHAR(160), token_hash VARCHAR(64) NOT NULL UNIQUE, created_by_id INTEGER NOT NULL REFERENCES users(id), expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ);
CREATE INDEX ix_invitations_email ON invitations(email); CREATE INDEX ix_invitations_token_hash ON invitations(token_hash);
CREATE TABLE children (id SERIAL PRIMARY KEY, first_name VARCHAR(100) NOT NULL, last_name VARCHAR(100) NOT NULL DEFAULT '', display_name VARCHAR(160) NOT NULL, birth_date DATE, school VARCHAR(200), school_class VARCHAR(80), care VARCHAR(200), notes TEXT, color VARCHAR(20) NOT NULL DEFAULT '#426B5E', is_active BOOLEAN NOT NULL DEFAULT true);
CREATE TABLE child_user_permissions (id SERIAL PRIMARY KEY, child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, permission child_permission NOT NULL, UNIQUE(child_id,user_id));
CREATE INDEX ix_child_user_permissions_child_id ON child_user_permissions(child_id); CREATE INDEX ix_child_user_permissions_user_id ON child_user_permissions(user_id);
CREATE TABLE calendar_sources (id SERIAL PRIMARY KEY, key VARCHAR(80) NOT NULL UNIQUE, name VARCHAR(160) NOT NULL, kind VARCHAR(40) NOT NULL, url VARCHAR(1000), is_active BOOLEAN NOT NULL DEFAULT true, last_sync_at TIMESTAMPTZ, last_result JSONB, last_error TEXT);
CREATE TABLE calendar_events (id SERIAL PRIMARY KEY, source_id INTEGER REFERENCES calendar_sources(id), child_id INTEGER REFERENCES children(id), external_id VARCHAR(300), title VARCHAR(300) NOT NULL, description TEXT, starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL, all_day BOOLEAN NOT NULL DEFAULT false, category VARCHAR(40) NOT NULL DEFAULT 'FAMILY', url VARCHAR(1000), raw_data JSONB, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(source_id,external_id));
CREATE INDEX ix_events_range ON calendar_events(starts_at,ends_at);
CREATE TABLE stays (id SERIAL PRIMARY KEY, child_id INTEGER NOT NULL REFERENCES children(id), responsible_user_id INTEGER NOT NULL REFERENCES users(id), starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL, status plan_status NOT NULL, created_by_id INTEGER NOT NULL REFERENCES users(id), note TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CHECK(ends_at > starts_at));
CREATE INDEX ix_stays_child_id ON stays(child_id); CREATE INDEX ix_stays_child_range ON stays(child_id,starts_at,ends_at);
CREATE TABLE recurrence_rules (id SERIAL PRIMARY KEY, child_id INTEGER NOT NULL REFERENCES children(id), responsible_user_id INTEGER NOT NULL REFERENCES users(id), rrule VARCHAR(500) NOT NULL, starts_at TIMESTAMPTZ NOT NULL, duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0));
CREATE TABLE holiday_periods (id SERIAL PRIMARY KEY, external_id VARCHAR(200) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL, starts_on DATE NOT NULL, ends_on DATE NOT NULL, state_code VARCHAR(2) NOT NULL DEFAULT 'HE', CHECK(ends_on >= starts_on));
CREATE TABLE holiday_plans (id SERIAL PRIMARY KEY, holiday_period_id INTEGER NOT NULL REFERENCES holiday_periods(id), child_id INTEGER NOT NULL REFERENCES children(id), status plan_status NOT NULL, created_by_id INTEGER NOT NULL REFERENCES users(id));
CREATE TABLE holiday_plan_segments (id SERIAL PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES holiday_plans(id) ON DELETE CASCADE, responsible_user_id INTEGER NOT NULL REFERENCES users(id), starts_on DATE NOT NULL, ends_on DATE NOT NULL, CHECK(ends_on >= starts_on));
CREATE TABLE change_requests (id SERIAL PRIMARY KEY, object_type VARCHAR(50) NOT NULL, object_id INTEGER NOT NULL, requested_by_id INTEGER NOT NULL REFERENCES users(id), affected_user_id INTEGER NOT NULL REFERENCES users(id), status plan_status NOT NULL, before_data JSONB NOT NULL, proposed_data JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE approvals (id SERIAL PRIMARY KEY, change_request_id INTEGER NOT NULL REFERENCES change_requests(id), user_id INTEGER NOT NULL REFERENCES users(id), decision VARCHAR(30) NOT NULL, comment TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE notifications (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), kind VARCHAR(50) NOT NULL, title VARCHAR(300) NOT NULL, body TEXT NOT NULL, read_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()); CREATE INDEX ix_notifications_user_id ON notifications(user_id);
CREATE TABLE api_tokens (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), name VARCHAR(160) NOT NULL, token_hash VARCHAR(64) NOT NULL UNIQUE, scopes JSONB NOT NULL, last_used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ);
CREATE TABLE audit_logs (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), action VARCHAR(100) NOT NULL, target_type VARCHAR(80), target_id VARCHAR(100), metadata JSONB, ip_address VARCHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT now()); CREATE INDEX ix_audit_logs_action ON audit_logs(action); CREATE INDEX ix_audit_logs_created_at ON audit_logs(created_at);
CREATE TABLE application_settings (key VARCHAR(100) PRIMARY KEY, value JSONB NOT NULL);
"""


def upgrade() -> None:
    op.execute(SCHEMA)


def downgrade() -> None:
    for table in ("application_settings","audit_logs","api_tokens","notifications","approvals","change_requests","holiday_plan_segments","holiday_plans","holiday_periods","recurrence_rules","stays","calendar_events","calendar_sources","child_user_permissions","children","invitations","sessions","users"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TYPE IF EXISTS plan_status; DROP TYPE IF EXISTS child_permission; DROP TYPE IF EXISTS role")
