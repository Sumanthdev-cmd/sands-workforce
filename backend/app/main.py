from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Backend API for the Workforce Management System.",
        debug=settings.debug,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
    )

    return application


app = create_application()


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    """Return basic API information."""

    return {
        "message": "Workforce Management API is running",
        "version": settings.app_version,
        "documentation": "/docs",
    }
