"""Catalogue-consistent counts; no employee/history mutations."""
from sqlalchemy import text

COUNTS_SQL = """
SELECT COUNT(*) AS employees,
       COALESCE(SUM(CASE WHEN u.is_active = TRUE AND e.employment_status = 'ACTIVE'
                         THEN 1 ELSE 0 END), 0) AS active_employees,
       COALESCE(SUM(CASE WHEN u.is_active = TRUE AND e.employment_status = 'ACTIVE'
                         THEN 0 ELSE 1 END), 0) AS disabled_employees
FROM employees e
JOIN users u ON u.id = e.user_id
WHERE e.organization_id = :org AND u.organization_id = :org
AND NOT EXISTS (
    SELECT 1 FROM workforce_catalogue_state cs
    WHERE cs.organization_id = e.organization_id AND cs.person_id = e.id
      AND cs.kind = 'employee' AND cs.archived_at IS NOT NULL
)
"""

def employee_counts(database, organization_id):
    row = database.execute(text(COUNTS_SQL), {"org": organization_id}).mappings().one()
    return {key: int(row[key] or 0) for key in
            ("employees", "active_employees", "disabled_employees")}
