from typing import Literal

from pydantic import BaseModel, Field


class PostScore(BaseModel):
    relevance_score: int = Field(ge=0, le=10)
    category: Literal["trend", "pain", "case", "idea", "other"]
    summary: str
    topics: list[str] = Field(default_factory=list, max_length=5)