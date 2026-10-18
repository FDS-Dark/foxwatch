from typing import Literal, Optional

from pydantic import BaseModel, Field


class IncidentRecoveryRequest(BaseModel):
    """Recovery suggestions are always derived from live bloom favorability and station inputs."""

    use_gemini: bool = True
    top_k: int = Field(default=8, ge=3, le=12)
    optional_notes: Optional[str] = Field(default=None, max_length=500)


RecoveryPriority = Literal["immediate", "short_term", "long_term"]
SuggestionCategory = Literal["algae_cleanup", "consequence_reduction"]
