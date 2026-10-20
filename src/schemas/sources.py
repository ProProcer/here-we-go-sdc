"""Trusted source configuration, shared by refresh and candidate extraction."""

from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from src.schemas.role import Contract, SourceId


class ApprovedSource(Contract):
    source_id: SourceId
    source_url: HttpUrl
    publisher: str = Field(min_length=1)
    published_at: date

    @model_validator(mode="after")
    def validate_url(self):
        url = self.source_url
        if url.scheme != "https" or url.username or url.password or url.fragment:
            raise ValueError(
                "Approved sources require HTTPS without credentials or fragments"
            )
        return self


class SourceRegistry(Contract):
    schema_version: Literal["0.1.0"]
    sources: list[ApprovedSource] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique(self):
        for field in ("source_id", "source_url"):
            values = [getattr(row, field) for row in self.sources]
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate approved {field}")
        return self
