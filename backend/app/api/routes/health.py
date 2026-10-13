from typing import Any

from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["System"])

settings = get_settings()


@router.get("/live")
def liveness_check() -> dict[str, str]:
    """Confirm that the FastAPI application is running."""

    return {
        "status": "alive",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/ready")
def readiness_check(response: Response) -> dict[str, Any]:
    """Check PostgreSQL and Redis availability."""

    database_status = "unavailable"
    redis_status = "unavailable"

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        database_status = "available"
    except Exception:
        database_status = "unavailable"

    redis_client: Redis | None = None

    try:
        redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

        if redis_client.ping():
            redis_status = "available"
    except Exception:
        redis_status = "unavailable"
    finally:
        if redis_client is not None:
            redis_client.close()

    is_ready = (
        database_status == "available"
        and redis_status == "available"
    )

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "degraded",
        "services": {
            "database": database_status,
            "redis": redis_status,
        },
    }
