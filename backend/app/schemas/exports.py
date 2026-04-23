from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExportMode = Literal["single_activity", "multi_activity", "date_range"]
ExportStatus = Literal["success", "error"]
BatchExportFormat = Literal["zip", "markdown"]


class MarkdownExportRequest(BaseModel):
    mode: ExportMode = "single_activity"
    activity_id: str | None = Field(default=None, min_length=1)
    date_from: date | None = None
    date_to: date | None = None
    activity_type: str = Field(default="running", min_length=1)
    max_activities: int = Field(default=30, ge=1, le=100)
    include_notes: bool = True
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_export_request(self) -> "MarkdownExportRequest":
        if self.mode == "single_activity" and self.activity_id is None:
            raise ValueError("activity_id is required for single_activity exports.")

        if self.mode == "date_range":
            if self.date_from is None or self.date_to is None:
                raise ValueError("date_from and date_to are required for date_range exports.")
            if self.date_from > self.date_to:
                raise ValueError("date_from must be before or equal to date_to.")

        return self


class MarkdownExportMetadata(BaseModel):
    activity_count: int = Field(ge=0)
    generated_at: str

    model_config = ConfigDict(extra="allow")


class MarkdownExportResponse(BaseModel):
    status: ExportStatus
    markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class BatchExportRequest(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=100)
    export_format: BatchExportFormat = "zip"
    include_notes: bool = True
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")
