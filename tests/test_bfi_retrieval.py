"""Tests for BFI hybrid retrieval and insight generation."""

import json
import unittest
from pathlib import Path

from api.services.bfi_scoring import calculate_bloom_favorability
from api.services.bfi_retrieval import (
    build_evidence_package,
    extract_dominant_drivers,
    hybrid_retrieve,
    retrieval_tags_for_drivers,
)
from api.services.rag_embeddings import EmbeddedChunk, HashEmbedder, ingest_document
from api.services.bfi_insights import compute_confidence, generate_bfi_insights, save_insight_example

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "data" / "rag" / "sources" / "sample_phosphorus_hydrology.txt"
EXAMPLES_DIR = REPO / "data" / "rag" / "examples" / "bfi_insights"


def _chunk(
    chunk_id: str,
    text: str,
    tags: list[str],
    *,
    title: str,
    source_type: str = "research_paper",
    section: str = "",
    chapter: str = "",
    priority: str = "high",
) -> EmbeddedChunk:
    embedder = HashEmbedder(dimensions=32)
    vector = embedder.embed([text])[0]
    return EmbeddedChunk(
        chunk_id=chunk_id,
        text=text,
        embedding=vector,
        metadata={
            "document_title": title,
            "source_type": source_type,
            "chapter": chapter,
            "section": section,
            "authors": "Test Author",
            "year": 2020,
            "chunk_id": chunk_id,
            "word_count": len(text.split()),
        },
        retrieval_summary=f"Summary for {chunk_id}",
        tags=tags,
        retrieval_priority=priority,
    )


class TestDriverExtraction(unittest.TestCase):
    def test_extracts_positive_drivers_sorted_by_points(self) -> None:
        bfi = {
            "classification": "HIGH FAVORABILITY",
            "score": 9,
            "factors": [
                {"factor": "water_temperature", "attribute": "water_temperature", "points": 2},
                {"factor": "phosphorus", "attribute": "orthophosphate_dissolved", "points": 2},
                {"factor": "discharge", "attribute": "discharge", "points": 1},
                {"factor": "precipitation", "attribute": "precipitation", "points": 0},
            ],
        }
        result = extract_dominant_drivers(bfi)
        self.assertEqual(result.drivers[:2], ["water_temperature", "phosphorus"])
        self.assertIn("discharge", result.drivers)


class TestHybridRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.embedder = HashEmbedder(dimensions=64)
        cls.index = [
            _chunk(
                "p1",
                "Elevated phosphorus and orthophosphate from watershed runoff increase "
                "cyanobacterial nutrient availability and eutrophication.",
                ["phosphorus", "orthophosphate", "nutrients", "runoff", "cyanobacteria"],
                title="HAB Ecology Review",
                section="Nutrient loading",
            ),
            _chunk(
                "d1",
                "Low streamflow and reduced discharge lengthen residence time and reduce flushing.",
                ["discharge", "streamflow", "hydrology", "residence_time"],
                title="River Hydrology and Blooms",
                section="Flow effects",
            ),
            _chunk(
                "t1",
                "Warmer water temperature and sunlight increase cyanobacteria growth rates.",
                ["temperature", "sunlight", "cyanobacteria"],
                title="WHO Cyanobacteria Guidance",
                source_type="who_guidance",
                chapter="Chapter 7",
                section="Growth conditions",
            ),
            _chunk(
                "x1",
                "Laboratory toxin monitoring protocols and public communication guidance.",
                ["water_quality"],
                title="Toxin Monitoring Manual",
                source_type="who_guidance",
                chapter="Chapter 2",
                section="Public communication",
                priority="low",
            ),
        ]

    def test_phosphorus_driver_retrieval(self) -> None:
        bfi = calculate_bloom_favorability(
            water_temperature_c=18.0,
            phosphorus_ug_l=80.0,
            nitrogen_mg_l=0.2,
            streamflow_cfs=200.0,
            seasonal_median_streamflow_cfs=150.0,
            rainfall_7day_in=0.1,
            solar_radiation_level="low",
        )
        ranked = hybrid_retrieve(bfi, self.index, self.embedder, top_k=3)
        top_ids = [r.chunk.chunk_id for r in ranked]
        self.assertIn("p1", top_ids)

    def test_discharge_driver_retrieval(self) -> None:
        bfi = calculate_bloom_favorability(
            water_temperature_c=18.0,
            phosphorus_ug_l=10.0,
            streamflow_cfs=80.0,
            seasonal_median_streamflow_cfs=150.0,
        )
        ranked = hybrid_retrieve(bfi, self.index, self.embedder, top_k=3)
        self.assertIn("d1", [r.chunk.chunk_id for r in ranked])

    def test_temperature_driver_retrieval(self) -> None:
        bfi = calculate_bloom_favorability(
            water_temperature_c=28.0,
            phosphorus_ug_l=10.0,
            solar_radiation_level="high",
        )
        ranked = hybrid_retrieve(bfi, self.index, self.embedder, top_k=3)
        self.assertIn("t1", [r.chunk.chunk_id for r in ranked])

    def test_source_filtering_penalizes_toxin_manual(self) -> None:
        bfi = calculate_bloom_favorability(
            water_temperature_c=28.0,
            phosphorus_ug_l=80.0,
            streamflow_cfs=80.0,
            seasonal_median_streamflow_cfs=150.0,
        )
        ranked = hybrid_retrieve(bfi, self.index, self.embedder, top_k=4)
        ids = [r.chunk.chunk_id for r in ranked]
        self.assertNotIn("x1", ids[:3])

    def test_hybrid_score_uses_tags_not_vector_only(self) -> None:
        tags = retrieval_tags_for_drivers(["phosphorus", "discharge"])
        self.assertIn("phosphorus", tags)
        self.assertIn("streamflow", tags)


class TestInsightGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.embedder = HashEmbedder(dimensions=64)
        if SAMPLE.is_file():
            cls.index = ingest_document(SAMPLE, embedder=cls.embedder)
        else:
            cls.index = TestHybridRetrieval.index

    def _payload_for(self, **kwargs: object) -> dict:
        bfi = calculate_bloom_favorability(**kwargs)
        return generate_bfi_insights(bfi, self.index, self.embedder)

    def test_confidence_scoring(self) -> None:
        bfi = calculate_bloom_favorability(water_temperature_c=27.0, phosphorus_ug_l=75.0)
        evidence = build_evidence_package(bfi, self.index, self.embedder)
        conf = compute_confidence(bfi, evidence)
        self.assertIn(conf.level, {"Low", "Moderate", "High"})
        self.assertGreaterEqual(conf.percent, 0)
        self.assertLessEqual(conf.percent, 100)

    def test_insight_payload_structure(self) -> None:
        payload = self._payload_for(
            water_temperature_c=27.0,
            phosphorus_ug_l=75.0,
            streamflow_cfs=80.0,
            seasonal_median_streamflow_cfs=150.0,
        )
        insights = payload["insights"]
        self.assertIn("executive_summary", insights)
        self.assertIn("scientific_interpretation", insights)
        self.assertIn("confidence", insights)
        self.assertIn("sources", insights)
        self.assertIn("gemini_prompt", payload)
        self.assertLessEqual(len(payload["evidence"]["supporting_chunks"]), 5)

    def test_write_classification_examples(self) -> None:
        EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        scenarios = {
            "low": dict(
                water_temperature_c=18.0,
                phosphorus_ug_l=10.0,
                nitrogen_mg_l=0.2,
                streamflow_cfs=200.0,
                seasonal_median_streamflow_cfs=150.0,
                rainfall_7day_in=0.1,
                solar_radiation_level="low",
            ),
            "moderate": dict(
                water_temperature_c=22.0,
                phosphorus_ug_l=30.0,
                nitrogen_mg_l=0.75,
                streamflow_cfs=150.0,
                seasonal_median_streamflow_cfs=150.0,
                rainfall_7day_in=1.0,
                solar_radiation_level="moderate",
            ),
            "high": dict(
                water_temperature_c=27.0,
                phosphorus_ug_l=75.0,
                nitrogen_mg_l=1.2,
                streamflow_cfs=150.0,
                seasonal_median_streamflow_cfs=150.0,
                rainfall_7day_in=1.0,
                solar_radiation_level="moderate",
            ),
            "very_high": dict(
                water_temperature_c=30.0,
                phosphorus_ug_l=100.0,
                nitrogen_mg_l=2.0,
                streamflow_cfs=50.0,
                seasonal_median_streamflow_cfs=150.0,
                rainfall_7day_in=3.0,
                solar_radiation_level="high",
            ),
        }
        for name, kwargs in scenarios.items():
            payload = self._payload_for(**kwargs)
            slim = {
                "bfi": payload["bfi"],
                "insights": payload["insights"],
                "evidence": {
                    "context_summary": payload["evidence"]["context_summary"],
                    "sources": payload["evidence"]["sources"],
                    "retrieval_tags": payload["evidence"]["retrieval_tags"],
                },
            }
            path = EXAMPLES_DIR / f"{name}_favorability.json"
            save_insight_example(str(path), slim)
            self.assertTrue(path.is_file())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("insights", loaded)


if __name__ == "__main__":
    unittest.main()
