from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AuthStartRequest(BaseModel):
    email: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class AuthCompleteRequest(BaseModel):
    auth_session_id: str = Field(min_length=1)
    mfa_code: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class AuthSessionResponse(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"

    model_config = ConfigDict(extra="forbid")


class LogoutResponse(BaseModel):
    status: Literal["logged_out"]
    message: str

    model_config = ConfigDict(extra="forbid")
