from typing import Literal

from pydantic import BaseModel, Field


class XrayQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    segment_id: Literal[17, 31, 32] = 32
