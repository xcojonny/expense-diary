from pydantic import BaseModel, Field


class LogEntryOut(BaseModel):
    """One captured log event for the admin log view."""

    timestamp: str | None = None
    level: str
    event: str
    logger: str | None = None
    context: dict[str, str] = Field(default_factory=dict)
