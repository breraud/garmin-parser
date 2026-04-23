import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


def hash_email(email: str) -> str:
    normalized_email = email.strip().lower()
    return hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthenticatedUser:
    email_hash: str


class TokenManager:
    def __init__(self, ttl_seconds: int = 60 * 60 * 12) -> None:
        self._ttl_seconds = ttl_seconds
        self._secret = os.urandom(32)

    def create_access_token(self, email: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": hash_email(email),
            "exp": int((now + timedelta(seconds=self._ttl_seconds)).timestamp()),
            "iat": int(now.timestamp()),
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded_payload = self._urlsafe_b64encode(payload_bytes)
        signature = hmac.new(self._secret, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        encoded_signature = self._urlsafe_b64encode(signature)
        return f"{encoded_payload}.{encoded_signature}"

    def verify_access_token(self, token: str) -> AuthenticatedUser:
        try:
            encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        except ValueError as exc:
            raise self._unauthorized("Invalid bearer token.") from exc

        expected_signature = hmac.new(
            self._secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        provided_signature = self._urlsafe_b64decode(encoded_signature)
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise self._unauthorized("Invalid bearer token.")

        try:
            payload = json.loads(self._urlsafe_b64decode(encoded_payload))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise self._unauthorized("Invalid bearer token.") from exc

        email_hash = payload.get("sub")
        expires_at = payload.get("exp")
        if not isinstance(email_hash, str) or not email_hash:
            raise self._unauthorized("Invalid bearer token.")
        if not isinstance(expires_at, int):
            raise self._unauthorized("Invalid bearer token.")
        if expires_at < int(datetime.now(UTC).timestamp()):
            raise self._unauthorized("Bearer token expired.")

        return AuthenticatedUser(email_hash=email_hash)

    def _unauthorized(self, detail: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    def _urlsafe_b64encode(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _urlsafe_b64decode(self, value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}")


token_bearer = HTTPBearer(auto_error=False)
token_manager = TokenManager()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(token_bearer),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    return token_manager.verify_access_token(credentials.credentials)
