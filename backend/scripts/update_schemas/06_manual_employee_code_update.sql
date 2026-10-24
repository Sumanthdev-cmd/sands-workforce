CREATE TABLE IF NOT EXISTS employee_code_reuse_history (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL REFERENCES organizations(id),
 original_code varchar(50) NOT NULL,
 retired_code varchar(50) NOT NULL,
 previous_user_id uuid NOT NULL REFERENCES users(id),
 previous_employee_id uuid NOT NULL REFERENCES employees(id),
 new_user_id uuid NOT NULL REFERENCES users(id),
 changed_by_user_id uuid NOT NULL REFERENCES users(id),
 changed_at timestamptz NOT NULL DEFAULT now()
);
