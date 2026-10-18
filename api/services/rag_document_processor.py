"""
Extract and clean scientific text from PDFs and plain-text sources for RAG ingestion.

Strips bibliographies, boilerplate, and navigation while preserving section structure
and paragraph boundaries for semantic chunking downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

# ---------------------------------------------------------------------------
# Patterns for content to drop
# ---------------------------------------------------------------------------

PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:page\s+)?\d+\s*(?:of\s+\d+)?\s*$",
    re.IGNORECASE,
)
ROMAN_PAGE_LINE = re.compile(r"^\s*[ivxlcdm]+\s*$", re.IGNORECASE)

SECTION_CUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*references\s*$", re.IGNORECASE),
    re.compile(r"^\s*bibliography\s*$", re.IGNORECASE),
    re.compile(r"^\s*literature\s+cited\s*$", re.IGNORECASE),
    re.compile(r"^\s*works\s+cited\s*$", re.IGNORECASE),
    re.compile(r"^\s*acknowledg(?:e)?ments\s*$", re.IGNORECASE),
    re.compile(r"^\s*appendix(?:es)?\s*[a-z0-9.\-]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*table\s+of\s+contents\s*$", re.IGNORECASE),
    re.compile(r"^\s*figure\s+index\s*$", re.IGNORECASE),
    re.compile(r"^\s*table\s+index\s*$", re.IGNORECASE),
    re.compile(r"^\s*list\s+of\s+(?:figures|tables)\s*$", re.IGNORECASE),
    re.compile(r"^\s*author\s+biograph(?:y|ies)\s*$", re.IGNORECASE),
)

HEADING_NUMBERED = re.compile(
    r"^(?P<num>(?:\d+\.)+\d*|\d+\.)\s+(?P<title>.+)$"
)
HEADING_CAPS = re.compile(r"^[A-Z][A-Z0-9\s,\-–—:]{3,80}$")

YEAR_IN_TEXT = re.compile(r"\b(19|20)\d{2}\b")
AUTHOR_LINE = re.compile(
    r"^(?:by\s+)?([A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+(?:and|&)\s+[A-Z][a-z]+(?:\s+[A-Z]\.)?)+)$"
)


@dataclass
class DocumentSection:
    """One logical section with preserved paragraphs."""

    title: str
    level: int
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class ProcessedDocument:
    """Cleaned document ready for semantic chunking."""

    document_title: str
    source_type: str
    authors: str
    year: Optional[int]
    chapter: str
    sections: list[DocumentSection]
    source_path: str


def infer_source_type(path: Path, override: Optional[str] = None) -> str:
    """Infer ``source_type`` from path or explicit override."""
    if override:
        return override
    name = path.name.lower()
    if "who" in name or "cyanobacter" in name:
        return "who_guidance"
    if "epa" in name or "habs" in name:
        return "epa_guidance"
    if "chapter" in name or "textbook" in name:
        return "textbook_chapter"
    return "research_paper"


def extract_pdf_text(path: Path) -> list[str]:
    """
    Extract text from a PDF as a list of page strings.

    Requires ``pypdf`` (``pip install pypdf``).
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "PDF ingestion requires pypdf. Install with: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def load_document_pages(path: Path) -> list[str]:
    """Load a document as page-like text blocks (PDF pages or single text file)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return [text]


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_cut_section(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(pat.match(stripped) for pat in SECTION_CUT_PATTERNS)


def _is_heading(line: str) -> tuple[bool, int, str]:
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False, 0, ""

    numbered = HEADING_NUMBERED.match(stripped)
    if numbered:
        depth = numbered.group("num").count(".")
        return True, min(depth, 4), numbered.group("title").strip()

    if HEADING_CAPS.match(stripped) and not stripped.endswith("."):
        return True, 1, stripped.title()

    if (
        len(stripped) < 80
        and stripped[0].isupper()
        and not stripped.endswith(".")
        and stripped.count(".") <= 1
        and len(stripped.split()) <= 12
    ):
        return True, 2, stripped

    return False, 0, ""


def _strip_page_artifacts(lines: list[str]) -> list[str]:
    """Remove page numbers and repeated header/footer lines."""
    if not lines:
        return lines

    counts: dict[str, int] = {}
    for line in lines:
        key = line.strip()
        if key:
            counts[key] = counts.get(key, 0) + 1

    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if PAGE_NUMBER_LINE.match(stripped) or ROMAN_PAGE_LINE.match(stripped):
            continue
        # Drop lines repeated on many "pages" (likely running headers/footers).
        if len(stripped) < 90 and counts.get(stripped, 0) >= 3:
            continue
        cleaned.append(stripped)
    return cleaned


def _lines_to_sections(lines: Iterable[str]) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    current = DocumentSection(title="Introduction", level=1, paragraphs=[])

    paragraph_buf: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_buf:
            return
        para = " ".join(paragraph_buf).strip()
        paragraph_buf.clear()
        if len(para.split()) >= 8:
            current.paragraphs.append(para)

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_paragraph()
            continue

        is_head, level, title = _is_heading(line)
        if is_head:
            flush_paragraph()
            if current.paragraphs or current.title != "Introduction":
                sections.append(current)
            current = DocumentSection(title=title, level=level, paragraphs=[])
            continue

        paragraph_buf.append(line)

    flush_paragraph()
    if current.paragraphs:
        sections.append(current)

    if not sections:
        sections.append(DocumentSection(title="Body", level=1, paragraphs=[]))

    return sections


def _truncate_before_back_matter(lines: list[str]) -> list[str]:
    """
    Drop back-matter starting at the first cut heading after meaningful body text.

    Ignores very early TOC-style headings (common on PDF cover pages).
    """
    cut_after = min(80, max(20, int(len(lines) * 0.55)))
    out: list[str] = []
    for idx, line in enumerate(lines):
        if idx >= cut_after and _is_cut_section(line):
            break
        out.append(line)
    return out


def _guess_title_and_authors(pages: list[str], path: Path) -> tuple[str, str, Optional[int]]:
    """Heuristic metadata from first page and filename."""
    title = path.stem.replace("_", " ").replace("-", " ").strip().title()
    authors = ""
    year: Optional[int] = None

    head = "\n".join(pages[:1]) if pages else ""
    for line in head.splitlines()[:30]:
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > 12 and len(stripped) < 120 and not authors:
            if AUTHOR_LINE.match(stripped):
                authors = stripped
        if year is None:
            match = YEAR_IN_TEXT.search(stripped)
            if match:
                year = int(match.group(0))

    return title, authors, year


def process_document(
    path: Path | str,
    *,
    document_title: Optional[str] = None,
    source_type: Optional[str] = None,
    authors: Optional[str] = None,
    year: Optional[int] = None,
    chapter: Optional[str] = None,
) -> ProcessedDocument:
    """
    Load, clean, and structure a scientific document.

    Args:
        path: Path to ``.pdf``, ``.txt``, or ``.md``.
        document_title: Override detected title.
        source_type: e.g. ``research_paper``, ``who_guidance``, ``epa_guidance``.
        authors: Override detected authors.
        year: Publication year.
        chapter: Chapter label for guidance volumes.

    Returns:
        ``ProcessedDocument`` with sectioned paragraphs.
    """
    doc_path = Path(path)
    pages = load_document_pages(doc_path)
    merged = _normalize_whitespace("\n\n".join(pages))
    lines = merged.splitlines()
    lines = _truncate_before_back_matter(lines)
    lines = _strip_page_artifacts(lines)

    guessed_title, guessed_authors, guessed_year = _guess_title_and_authors(pages, doc_path)
    sections = _lines_to_sections(lines)

    return ProcessedDocument(
        document_title=document_title or guessed_title,
        source_type=infer_source_type(doc_path, source_type),
        authors=authors or guessed_authors,
        year=year if year is not None else guessed_year,
        chapter=chapter or "",
        sections=sections,
        source_path=str(doc_path.resolve()),
    )


def iter_paragraphs(document: ProcessedDocument) -> Iterator[tuple[str, str, str]]:
    """
    Yield ``(chapter, section_title, paragraph_text)`` for chunking.

    ``chapter`` uses document-level chapter when set, otherwise section title.
    """
    for section in document.sections:
        chapter = document.chapter or section.title
        for para in section.paragraphs:
            yield chapter, section.title, para
