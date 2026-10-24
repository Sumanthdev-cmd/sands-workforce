CREATE TABLE IF NOT EXISTS workforce_catalogue_state (
 organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
 kind varchar(10) NOT NULL CHECK (kind IN ('employee','vendor')),
 person_id uuid NOT NULL,
 last_working_day date,
 separation_reason text,
 settled_on date,
 settled_by uuid REFERENCES users(id) ON DELETE RESTRICT,
 settlement_reference varchar(200),
 settlement_note text,
 archived_at timestamptz,
 archived_by uuid REFERENCES users(id) ON DELETE RESTRICT,
 PRIMARY KEY (organization_id,kind,person_id),
 CHECK (archived_at IS NULL OR (settled_on IS NOT NULL AND settled_by IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS workforce_catalogue_events (
 id bigserial PRIMARY KEY,
 organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
 kind varchar(10) NOT NULL,
 person_id uuid NOT NULL,
 action varchar(30) NOT NULL,
 actor_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 details jsonb NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_workforce_employee_current_location
 ON location_history (organization_id,employee_id,recorded_at DESC);
CREATE INDEX IF NOT EXISTS ix_workforce_vendor_session_location
 ON mobile_vendor_locations (organization_id,vendor_id,attendance_id,recorded_at DESC);
