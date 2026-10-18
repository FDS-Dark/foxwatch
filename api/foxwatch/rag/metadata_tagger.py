"""
Automatic scientific tagging and retrieval summaries for RAG chunks.

Prioritizes environmental mechanisms and bloom drivers over toxicology, lab methods,
and administrative guidance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from .chunker import ChunkRecord

RetrievalPriority = Literal["high", "medium", "low"]

# Canonical tag vocabulary (subset enforced; unknown tags from rules are dropped).
ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "phosphorus",
        "nitrate",
        "orthophosphate",
        "nutrients",
        "temperature",
        "sunlight",
        "solar_radiation",
        "streamflow",
        "discharge",
        "residence_time",
        "hydrology",
        "precipitation",
        "runoff",
        "eutrophication",
        "stratification",
        "mixing",
        "cyanobacteria",
        "harmful_algal_bloom",
        "bloom_prediction",
        "water_quality",
    }
)

TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "phosphorus",
        (
            r"\bphosphorus\b",
            r"\bphosphate\b",
            r"\bphosphates\b",
            r"\bp\b(?=\s*(?:limit|concentration|loading))",
        ),
    ),
    ("orthophosphate", (r"\borthophosphate\b", r"\bpo4\b", r"\bdissolved phosphorus\b")),
    ("nitrate", (r"\bnitrate\b", r"\bnitrite\b", r"\bnitrogen\b", r"\binorganic nitrogen\b")),
    ("nutrients", (r"\bnutrient\b", r"\bnutrients\b", r"\beutroph\b", r"\bmacronutrient\b")),
    ("temperature", (r"\btemperature\b", r"\bthermal\b", r"\bwarming\b", r"\bdeg(c|rees)\b")),
    (
        "sunlight",
        (r"\bsunlight\b", r"\blight availability\b", r"\bphotosynthetically active\b", r"\bpar\b"),
    ),
    ("solar_radiation", (r"\bsolar radiation\b", r"\birradiance\b", r"\bsolar\b")),
    (
        "streamflow",
        (r"\bstreamflow\b", r"\blow flow\b", r"\bbaseflow\b", r"\bflow velocity\b"),
    ),
    (
        "discharge",
        (r"\bdischarge\b", r"\briver flow\b", r"\bhydraulic\b", r"\bcubic feet per second\b"),
    ),
    (
        "residence_time",
        (r"\bresidence time\b", r"\bwater retention\b", r"\bdetention time\b"),
    ),
    (
        "hydrology",
        (r"\bhydrolog\b", r"\bwatershed\b", r"\bflushing\b", r"\bwater level\b"),
    ),
    (
        "precipitation",
        (r"\bprecipitation\b", r"\brainfall\b", r"\bstorm event\b", r"\bstormwater\b"),
    ),
    (
        "runoff",
        (r"\brunoff\b", r"\bnonpoint source\b", r"\btile drainage\b", r"\boverland flow\b"),
    ),
    (
        "eutrophication",
        (r"\beutrophication\b", r"\bnutrient enrichment\b", r"\balgal enrichment\b"),
    ),
    (
        "stratification",
        (r"\bstratification\b", r"\bthermocline\b", r"\bvertical stability\b"),
    ),
    ("mixing", (r"\bmixing\b", r"\bturbulence\b", r"\bturnover\b", r"\bdestratification\b")),
    (
        "cyanobacteria",
        (
            r"\bcyanobacter\w*\b",
            r"\bblue[- ]green alga\w*\b",
            r"\bmicrocystis\b",
            r"\banabaena\b",
        ),
    ),
    (
        "harmful_algal_bloom",
        (r"\bharmful algal bloom\b", r"\bhab\b", r"\balgal bloom\b", r"\bbloom formation\b"),
    ),
    (
        "bloom_prediction",
        (r"\bbloom forecast\b", r"\bbloom prediction\b", r"\bearly warning\b"),
    ),
    (
        "water_quality",
        (r"\bwater quality\b", r"\btrophic state\b", r"\bimpairment\b"),
    ),
)

MECHANISM_PRIORITY_TERMS = (
    "nutrient",
    "phosphorus",
    "nitrogen",
    "runoff",
    "streamflow",
    "discharge",
    "temperature",
    "sunlight",
    "stratification",
    "cyanobacter",
    "bloom",
    "eutroph",
    "precipitation",
    "hydrolog",
)

DEPRIORITIZE_TERMS = (
    "toxicity",
    "toxin",
    "microcystin",
    "laboratory method",
    "sampling protocol",
    "quality assurance",
    "administrative",
    "regulatory compliance",
    "monitoring program design",
    "chain of custody",
    "lc-ms",
    "elisa kit",
)


@dataclass
class TaggedChunk:
    """Chunk with tags, summary, and retrieval priority."""

    chunk: ChunkRecord
    tags: list[str]
    retrieval_summary: str
    retrieval_priority: RetrievalPriority


def _compile_rules() -> list[tuple[str, re.Pattern[str]]]:
    return [(tag, re.compile("|".join(patterns), re.IGNORECASE)) for tag, patterns in TAG_RULES]


_COMPILED = _compile_rules()


def assign_tags(text: str, *, allowed: Iterable[str] = ALLOWED_TAGS) -> list[str]:
    """Return sorted tags matched in ``text``."""
    allowed_set = set(allowed)
    found: set[str] = set()
    for tag, pattern in _COMPILED:
        if tag not in allowed_set:
            continue
        if pattern.search(text):
            found.add(tag)
    return sorted(found)


def retrieval_priority(text: str, tags: list[str]) -> RetrievalPriority:
    """
    Rank chunks for mechanism-focused retrieval.

    High: bloom drivers / ecology; Low: toxicology, lab, admin content.
    """
    lower = text.lower()
    deprior = sum(1 for term in DEPRIORITIZE_TERMS if term in lower)
    mechanism = sum(1 for term in MECHANISM_PRIORITY_TERMS if term in lower)
    driver_tags = {
        "phosphorus",
        "nutrients",
        "streamflow",
        "discharge",
        "precipitation",
        "runoff",
        "temperature",
        "sunlight",
        "cyanobacteria",
        "harmful_algal_bloom",
    }
    has_driver = bool(driver_tags.intersection(tags))

    if deprior >= 2 and not has_driver:
        return "low"
    if has_driver and mechanism >= 2:
        return "high"
    if has_driver or mechanism >= 1:
        return "medium"
    return "low"


def generate_retrieval_summary(text: str, tags: list[str]) -> str:
    """
    Build a concise extractive summary for embedding / display.

    Uses the first complete sentence plus dominant environmental theme from tags.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    first = sentences[0].strip() if sentences else text.strip()[:200]
    if not first.endswith((".", "!", "?")):
        first = first + "."

    theme_map = {
        "phosphorus": "phosphorus and watershed nutrient loading",
        "runoff": "runoff-driven nutrient delivery",
        "streamflow": "streamflow and hydrologic flushing",
        "discharge": "river discharge and transport",
        "precipitation": "precipitation and storm-driven loading",
        "temperature": "temperature controls on algal growth",
        "sunlight": "light availability for photosynthesis",
        "cyanobacteria": "cyanobacteria ecology",
        "harmful_algal_bloom": "harmful algal bloom formation",
        "stratification": "thermal stratification and mixing",
    }
    theme = next((theme_map[t] for t in tags if t in theme_map), "environmental bloom drivers")

    if len(first) > 240:
        first = first[:237].rsplit(" ", 1)[0] + "..."

    return f"This section explains {theme}. {first}"


def tag_chunks(chunks: list[ChunkRecord]) -> list[TaggedChunk]:
    """Annotate each chunk with tags, summary, and retrieval priority."""
    tagged: list[TaggedChunk] = []
    for chunk in chunks:
        tags = assign_tags(chunk.text)
        summary = generate_retrieval_summary(chunk.text, tags)
        priority = retrieval_priority(chunk.text, tags)
        chunk.tags = tags
        chunk.retrieval_summary = summary
        tagged.append(
            TaggedChunk(
                chunk=chunk,
                tags=tags,
                retrieval_summary=summary,
                retrieval_priority=priority,
            )
        )
    return tagged
