from __future__ import annotations

import argparse

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import Candidate, CompanyAsset, JobApplication, JobVacancy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-local-development",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.confirm_local_development:
        raise SystemExit(
            "Add --confirm-local-development. Do not run this in production."
        )

    database = SessionLocal()
    try:
        vacancy_ids = list(
            database.scalars(
                select(JobVacancy.id).where(
                    JobVacancy.title.like("Bulk Test%")
                )
            ).all()
        )
        candidate_ids = list(
            database.scalars(
                select(Candidate.id).where(
                    Candidate.full_name == "Bulk Test Candidate"
                )
            ).all()
        )

        if vacancy_ids or candidate_ids:
            database.execute(
                delete(JobApplication).where(
                    (JobApplication.vacancy_id.in_(vacancy_ids))
                    | (JobApplication.candidate_id.in_(candidate_ids))
                )
            )
        if candidate_ids:
            database.execute(
                delete(Candidate).where(Candidate.id.in_(candidate_ids))
            )
        if vacancy_ids:
            database.execute(
                delete(JobVacancy).where(JobVacancy.id.in_(vacancy_ids))
            )

        asset_result = database.execute(
            delete(CompanyAsset).where(
                CompanyAsset.asset_code.like("BULK-%")
            )
        )
        database.commit()

        print("Deleted bulk-test applications:", "related rows")
        print("Deleted bulk-test candidates:", len(candidate_ids))
        print("Deleted bulk-test vacancies:", len(vacancy_ids))
        print("Deleted bulk-test assets:", asset_result.rowcount or 0)
    finally:
        database.close()


if __name__ == "__main__":
    main()
