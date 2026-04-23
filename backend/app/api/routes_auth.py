from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.routes_exports import (
    get_garmin_client_registry_dependency,
    raise_garmin_http_exception,
)
from app.core.auth import AuthenticatedUser, get_current_user, hash_email, token_manager
from app.garmin.exceptions import GarminClientError
from app.garmin.registry import GarminClientRegistry
from app.schemas.auth import (
    AuthSessionResponse,
    AuthStartRequest,
    LogoutResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthSessionResponse)
async def login_with_credentials(
    request: AuthStartRequest,
    registry: Annotated[
        GarminClientRegistry,
        Depends(get_garmin_client_registry_dependency),
    ],
) -> AuthSessionResponse:
    garmin_client = registry.get_client(hash_email(request.email))
    try:
        garmin_client.login(request.email, request.password.get_secret_value())
    except GarminClientError as exc:
        raise_garmin_http_exception(exc)

    access_token = token_manager.create_access_token(request.email)
    return AuthSessionResponse(access_token=access_token, token_type="bearer")


@router.post("/logout", response_model=LogoutResponse)
async def logout_session(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    registry: Annotated[
        GarminClientRegistry,
        Depends(get_garmin_client_registry_dependency),
    ],
) -> LogoutResponse:
    registry.logout(current_user.email_hash)

    return LogoutResponse(status="logged_out", message="Garmin session cleared.")
