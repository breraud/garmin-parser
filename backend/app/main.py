from fastapi import FastAPI

from app.api.routes_activities import router as activities_router
from app.api.routes_auth import router as auth_router
from app.api.routes_exports import router as exports_router
from app.api.routes_health import router as health_router
from app.core.config import get_settings
from app.core.cors import configure_cors


def create_app() -> FastAPI:
    app = FastAPI(title="Garmin Scraper API")
    settings = get_settings()

    configure_cors(app, settings)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(activities_router)
    app.include_router(exports_router)

    return app


app = create_app()
