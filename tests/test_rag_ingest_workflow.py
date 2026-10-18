"""Tests for FoxWatch RAG ingestion workflow helpers."""

import unittest
from pathlib import Path

from api.rag.ingest import (
    REQUIRED_CORPUS_KEYS,
    infer_ingest_kwargs,
    match_known_source,
    missing_required_sources,
    build_source_manifest,
)

REPO = Path(__file__).resolve().parents[1]


class TestKnownSourceInference(unittest.TestCase):
    def test_who_chapter_7_filename(self) -> None:
        path = Path("WHO-Cyanobacteria-Chapter-7.pdf")
        rule = match_known_source(path)
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule.key, "who_chapter_7")
        kwargs = infer_ingest_kwargs(path)
        self.assertEqual(kwargs["source_type"], "who_guidance")
        self.assertEqual(kwargs["chapter"], "Chapter 7")

    def test_epa_guidance_filename(self) -> None:
        path = Path("EPA-HAB-Guidance-2024.pdf")
        rule = match_known_source(path)
        self.assertIsNotNone(rule)
        kwargs = infer_ingest_kwargs(path)
        self.assertEqual(kwargs["source_type"], "epa_guidance")

    def test_litchman_2023_filename(self) -> None:
        path = Path("Litchman_2023_HAB_ecology.pdf")
        rule = match_known_source(path)
        self.assertIsNotNone(rule)
        kwargs = infer_ingest_kwargs(path)
        self.assertEqual(kwargs["source_type"], "peer_reviewed_paper")
        self.assertEqual(kwargs["year"], 2023)

    def test_missing_required_sources_detected(self) -> None:
        files = [REPO / "data" / "rag" / "sources" / "sample_phosphorus_hydrology.txt"]
        manifest = build_source_manifest(files)
        missing = missing_required_sources(manifest)
        self.assertEqual(set(missing), set(REQUIRED_CORPUS_KEYS))


if __name__ == "__main__":
    unittest.main()
