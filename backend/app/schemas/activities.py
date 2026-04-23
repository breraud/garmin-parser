from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ActivitySummary(BaseModel):
    activity_id: str = Field(min_length=1)
    date: date
    title: str | None = None
    distance_km: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")
