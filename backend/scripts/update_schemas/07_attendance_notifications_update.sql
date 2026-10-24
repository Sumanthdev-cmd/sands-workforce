ALTER TABLE notifications ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
