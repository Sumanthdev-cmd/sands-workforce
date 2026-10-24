CREATE TABLE IF NOT EXISTS employee_code_reservations(
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id),
 code varchar(50) NOT NULL, role_codes text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), consumed_at timestamptz,
 UNIQUE(organization_id,code)
);
CREATE TABLE IF NOT EXISTS geofence_alert_state(
 attendance_id uuid PRIMARY KEY REFERENCES attendance_records(id),
 organization_id uuid NOT NULL REFERENCES organizations(id),
 last_recorded_at timestamptz NOT NULL,
 outside boolean NOT NULL DEFAULT false,
 episode integer NOT NULL DEFAULT 0
);
