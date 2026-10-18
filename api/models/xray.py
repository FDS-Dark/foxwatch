from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class XrayQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    segment_id: Literal[17, 31, 32] = 32


class LiveXrayQuestion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    question: str = Field(default="Explain this prediction and its limitations.", min_length=1, max_length=1000)
    use_gemini: bool = True
