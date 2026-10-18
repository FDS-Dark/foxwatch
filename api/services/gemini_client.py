"""Gemini-backed insight generation (optional; requires GEMINI_API_KEY)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Mapping, Optional

from dotenv import load_dotenv

from settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MODEL_FALLBACKS,
    REPO_ROOT,
)

logger = logging.getLogger(__name__)

_JSON_SUFFIX = (
    "\n\nRespond with a single JSON object only (no markdown fences) using keys: "
    "executive_summary, bloom_assessment, key_contributing_factors (array), "
    "scientific_interpretation, confidence (object with level, percent, reason), sources (array)."
)


def _api_key() -> str:
    load_dotenv(REPO_ROOT / ".env", override=False)
    return os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()


def _model_candidates() -> list[str]:
    load_dotenv(REPO_ROOT / ".env", override=False)
    primary = os.getenv("GEMINI_MODEL", GEMINI_MODEL).strip() or GEMINI_MODEL
    seen: set[str] = set()
    ordered: list[str] = []
    for name in (primary, *GEMINI_MODEL_FALLBACKS):
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def gemini_configured() -> bool:
    return bool(_api_key())


def model_candidates() -> list[str]:
    return _model_candidates()


def generate_structured_insights(prompt: str) -> tuple[Optional[dict[str, Any]], str]:
    """
    Call Gemini with a grounded prompt and parse JSON-shaped insight output.

    Returns:
        (parsed_insights or None, mode) where mode is ``gemini`` or ``error:...``
    """
    api_key = _api_key()
    if not api_key:
        return None, "missing_api_key"

    try:
        import google.generativeai as genai
    except ImportError:
        return None, "missing_google_generativeai"

    genai.configure(api_key=api_key)
    full_prompt = prompt + _JSON_SUFFIX
    last_error = "unknown"

    for model_name in _model_candidates():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            text = (response.text or "").strip()
            parsed = _extract_json_object(text)
            if parsed is None:
                last_error = f"parse_error:{model_name}"
                continue
            return parsed, f"gemini:{model_name}"
        except Exception as exc:  # noqa: BLE001 — API/model errors vary by SDK version
            last_error = f"{model_name}:{type(exc).__name__}"
            logger.warning("Gemini model %s failed: %s", model_name, exc)

    return None, f"error:{last_error}"


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def merge_gemini_insights(
    baseline: Mapping[str, Any],
    gemini_payload: Mapping[str, Any],
    *,
    model_tag: str = "gemini",
) -> dict[str, Any]:
    """Prefer Gemini narrative fields; keep baseline sources if Gemini omits them."""
    merged = dict(baseline)
    for key in (
        "executive_summary",
        "bloom_assessment",
        "key_contributing_factors",
        "scientific_interpretation",
    ):
        if key in gemini_payload and gemini_payload[key]:
            merged[key] = gemini_payload[key]
    # Keep baseline confidence and RAG-structured sources; Gemini often returns
    # free-text citation strings that do not match the UI schema.
    merged["generation_mode"] = model_tag
    return merged
