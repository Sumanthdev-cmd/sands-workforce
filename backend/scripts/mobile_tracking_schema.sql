CREATE TABLE IF NOT EXISTS mobile_vendor_locations (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    attendance_id UUID NOT NULL REFERENCES vendor_attendance_records(id) ON DELETE CASCADE,
    client_event_id UUID NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy_meters DOUBLE PRECISION NOT NULL CHECK (accuracy_meters >= 0),
    speed_mps DOUBLE PRECISION,
    battery_percentage INTEGER CHECK (battery_percentage BETWEEN 0 AND 100),
    recorded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, vendor_id, client_event_id)
);
CREATE INDEX IF NOT EXISTS ix_mobile_vendor_location_recent
ON mobile_vendor_locations (organization_id, vendor_id, recorded_at DESC);
