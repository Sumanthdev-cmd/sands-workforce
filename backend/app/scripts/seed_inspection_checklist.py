from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import InspectionTemplate, Organization


TEMPLATE_FILE = Path(__file__).with_name("inspection_template.json")


def main():
    template_data = json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))

    with SessionLocal() as database:
        organizations = list(database.scalars(select(Organization)).all())
        if not organizations:
            raise SystemExit("No organizations found. Seed the organization first.")

        created = 0
        existing = 0
        for organization in organizations:
            row = database.scalar(
                select(InspectionTemplate).where(
                    InspectionTemplate.organization_id == organization.id,
                    InspectionTemplate.code == template_data["code"],
                    InspectionTemplate.version == template_data["version"],
                )
            )
            if row is not None:
                existing += 1
                continue

            database.add(
                InspectionTemplate(
                    organization_id=organization.id,
                    code=template_data["code"],
                    title=template_data["title"],
                    version=template_data["version"],
                    schema_data=template_data,
                    is_active=True,
                )
            )
            created += 1

        database.commit()
        print(f"Inspection templates created: {created}")
        print(f"Inspection templates already present: {existing}")


if __name__ == "__main__":
    main()
