from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # On passe en production pour désactiver les comportements de dev
    app_env: str = Field(default="production", alias="APP_ENV")
    
    # IMPORTANT : Dans un container Docker, api_host DOIT être 0.0.0.0 
    # pour que le port mapping (3567:3567) fonctionne.
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=3567, alias="API_PORT")
    
    # On ajoute ton domaine dans les origines autorisées pour corriger le CORS
    frontend_origin: str = Field(
        default="https://garmin.beraud.dev,http://garmin.beraud.dev,http://localhost:3568", 
        alias="FRONTEND_ORIGIN"
    )
    
    garmin_cache_ttl_seconds: int = Field(default=900, alias="GARMIN_CACHE_TTL_SECONDS")
    garmin_min_request_interval_seconds: int = Field(
        default=2,
        alias="GARMIN_MIN_REQUEST_INTERVAL_SECONDS",
    )
    garmin_email: str | None = Field(default=None, alias="GARMIN_EMAIL")
    garmin_password: SecretStr | None = Field(default=None, alias="GARMIN_PASSWORD")
    auth_session_ttl_seconds: int = Field(default=600, alias="AUTH_SESSION_TTL_SECONDS")

    model_config = SettingsConfigDict(
        # Il va chercher dans le .env à la racine du projet ou du backend
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def allowed_origins(self) -> list[str]:
        # Découpe la chaîne par les virgules pour créer la liste CORS
        origins = [
            origin.strip()
            for origin in self.frontend_origin.split(",")
            if origin.strip()
        ]
        return list(dict.fromkeys(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()
