"""Gemini-backed insight generation (optional; requires GEMINI_API_KEY)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse

from dotenv import load_dotenv

from settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MODEL_FALLBACKS,
    REPO_ROOT,
)

logger = logging.getLogger(__name__)

_NARRATIVE_JSON_SUFFIX = (
    "\n\nRespond with a single JSON object only (no markdown fences) using keys: "
    "executive_summary, bloom_assessment, key_contributing_factors (array), "
    "scientific_interpretation, confidence (object with level, percent, reason). "
    "executive_summary and scientific_interpretation must be plain language for field analysts: "
    "no paper titles, no author names, no [Evidence N] tags. "
    "Ground narrative in the evidence blocks provided; do not invent studies."
)

_EXTERNAL_SOURCES_JSON_SUFFIX = (
    "\n\nRespond with a single JSON object only (no markdown fences) using key: "
    "external_sources (array of 3–5 objects with name, organization, summary, url). "
    "Each summary must be 2–3 complete sentences describing what the program publishes "
    "and why it matters for bloom drivers (nutrients, flow, temperature, public health). "
    "Each url must be a full https link to an official program or guidance page you found via search. "
    "Prefer U.S. federal (.gov), Wisconsin state, WHO, NOAA, and USGS sources relevant to "
    "Green Bay / Lower Fox River harmful algal blooms and nutrient drivers. "
    "Do not list PDF titles, journal articles, or internal document indexes as sources."
)

_TRUSTED_HOST_FRAGMENTS = (
    ".gov",
    "who.int",
    "usgs.gov",
    "noaa.gov",
    "wisconsin.gov",
    "epa.gov",
    "glos.us",
    "coastalscience.noaa.gov",
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


def _url_trusted(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    return any(fragment in host for fragment in _TRUSTED_HOST_FRAGMENTS)


def _urls_from_grounding_metadata(response: Any) -> list[str]:
    urls: list[str] = []
    try:
        candidate = response.candidates[0]
        grounding = getattr(candidate, "grounding_metadata", None)
        if not grounding:
            return urls
        chunks = getattr(grounding, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                uri = str(web.uri).strip()
                if _url_trusted(uri):
                    urls.append(uri)
    except (AttributeError, IndexError, TypeError):
        return urls
    return urls


def _normalize_external_sources(
    raw: Sequence[Mapping[str, Any]],
    *,
    grounding_urls: Sequence[str],
) -> list[dict[str, Any]]:
    pool = list(grounding_urls)
    out: list[dict[str, Any]] = []
    for item in raw:
        name = str(item.get("name") or item.get("title") or "").strip()
        org = str(item.get("organization") or "").strip()
        summary = str(item.get("summary") or "").strip()
        url = str(item.get("url") or "").strip()
        if not _url_trusted(url):
            url = ""
        while not url and pool:
            candidate = pool.pop(0)
            if _url_trusted(candidate):
                url = candidate
        if not name:
            continue
        out.append(
            {
                "name": name,
                "organization": org or name,
                "summary": summary,
                "url": url,
                "source_origin": "web_search",
            }
        )
        if len(out) >= 5:
            break
    return out


def _search_tool_variants() -> list[Any]:
    variants: list[Any] = []
    try:
        from google.generativeai.types import GoogleSearchRetrieval, Tool

        variants.append([Tool(google_search_retrieval=GoogleSearchRetrieval())])
    except Exception:
        pass
    variants.append("google_search_retrieval")
    return variants


def discover_external_sources(discovery_prompt: str) -> tuple[list[dict[str, Any]], str]:
    """
    Use Gemini + Google Search to find real official sources (not the RAG index).
    """
    api_key = _api_key()
    if not api_key:
        return [], "missing_api_key"

    try:
        import google.generativeai as genai
    except ImportError:
        return [], "missing_google_generativeai"

    genai.configure(api_key=api_key)
    full_prompt = discovery_prompt + _EXTERNAL_SOURCES_JSON_SUFFIX
    last_error = "unknown"

    for model_name in _model_candidates():
        for tools in _search_tool_variants():
            try:
                model = genai.GenerativeModel(model_name, tools=tools)
                response = model.generate_content(full_prompt)
                text = (response.text or "").strip()
                parsed = _extract_json_object(text)
                if not parsed:
                    last_error = f"parse_error:{model_name}"
                    continue
                raw_list = parsed.get("external_sources") or parsed.get("public_sources") or []
                if not raw_list:
                    last_error = f"empty_sources:{model_name}"
                    continue
                grounding_urls = _urls_from_grounding_metadata(response)
                normalized = _normalize_external_sources(raw_list, grounding_urls=grounding_urls)
                if normalized:
                    return normalized, f"gemini_search:{model_name}"
            except Exception as exc:  # noqa: BLE001
                last_error = f"{model_name}:{type(exc).__name__}"
                logger.warning("External source discovery failed (%s): %s", model_name, exc)

    return [], f"error:{last_error}"


def generate_grounded_text(prompt: str) -> tuple[Optional[str], str]:
    """Plain-language answer grounded in the prompt (no JSON parsing)."""
    api_key = _api_key()
    if not api_key:
        return None, "missing_api_key"

    try:
        import google.generativeai as genai
    except ImportError:
        return None, "missing_google_generativeai"

    genai.configure(api_key=api_key)
    suffix = (
        "\n\nAnswer in clear prose for water-resource staff (2–4 short paragraphs). "
        "Cite evidence as [Evidence N] when making claims. "
        "State limitations if the passages do not fully answer the question."
    )
    last_error = "unknown"
    for model_name in _model_candidates():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt + suffix)
            text = (response.text or "").strip()
            if text:
                return text, f"gemini:{model_name}"
        except Exception as exc:
            last_error = f"{model_name}:{type(exc).__name__}"
            logger.warning("Gemini model %s failed: %s", model_name, exc)
    return None, f"error:{last_error}"


def generate_grounded_json(instructions: str, evidence: dict[str, Any]) -> tuple[dict | None, str]:
    """Bounded REST request using the same Gemini configuration as BFI.

    Uses the API's existing httpx dependency, including installations without
    the optional RAG SDK. Never log response bodies, prompts or credentials.
    """
    import time
    from urllib.parse import quote
    import httpx

    key = _api_key()
    if not key:
        return None, "missing_api_key"
    deadline = time.monotonic() + 40
    last_error = "unavailable"
    with httpx.Client() as client:
        for name in _model_candidates():
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                break
            try:
                response = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{quote(name.removeprefix('models/'), safe='')}:generateContent",
                    headers={"x-goog-api-key": key},
                    json={
                        "systemInstruction": {"parts": [{"text": instructions}]},
                        "contents": [{"role": "user", "parts": [{"text": json.dumps(evidence)}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
                    },
                    timeout=httpx.Timeout(min(18, remaining), connect=5),
                )
                if response.status_code != 200:
                    last_error = f"http_{response.status_code}"
                    if response.status_code in (401, 403, 429):
                        break
                    continue
                candidates = response.json().get("candidates", [])
                parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                parsed = _extract_json_object("".join(p.get("text", "") for p in parts if not p.get("thought")))
                if isinstance(parsed, dict):
                    return parsed, f"gemini:{name}"
                last_error = "invalid_response"
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
                last_error = "request_failed"
    return None, last_error


def generate_structured_json(
    prompt: str,
    *,
    json_suffix: str,
) -> tuple[Optional[dict[str, Any]], str]:
    """
    Call Gemini with a grounded prompt and parse a JSON object response.

    Returns:
        (parsed dict or None, mode) where mode is ``gemini:...`` or ``error:...``
    """
    api_key = _api_key()
    if not api_key:
        return None, "missing_api_key"

    try:
        import google.generativeai as genai
    except ImportError:
        return None, "missing_google_generativeai"

    genai.configure(api_key=api_key)
    full_prompt = prompt + json_suffix
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


def generate_structured_insights(prompt: str) -> tuple[Optional[dict[str, Any]], str]:
    """
    Call Gemini with a grounded prompt and parse JSON-shaped insight output.

    Returns:
        (parsed_insights or None, mode) where mode is ``gemini`` or ``error:...``
    """
    return generate_structured_json(prompt, json_suffix=_NARRATIVE_JSON_SUFFIX)


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
    """Prefer Gemini narrative fields; sources are discovered separately."""
    merged = dict(baseline)
    for key in (
        "executive_summary",
        "bloom_assessment",
        "key_contributing_factors",
        "scientific_interpretation",
    ):
        if key in gemini_payload and gemini_payload[key]:
            merged[key] = gemini_payload[key]
    if gemini_payload.get("confidence"):
        merged["confidence"] = gemini_payload["confidence"]
    merged["generation_mode"] = model_tag
    merged["rag_grounded"] = True
    return merged
