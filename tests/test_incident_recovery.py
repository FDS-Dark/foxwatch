import unittest

from api.services.incident_recovery import (
    _attach_sources,
    _build_retrieval_query,
    _fallback_suggestions,
    _format_current_conditions,
)


class IncidentRecoveryQueryTests(unittest.TestCase):
    def test_query_uses_bfi_not_free_text(self) -> None:
        bfi = {
            "classification": "MODERATE FAVORABILITY",
            "score": 6,
            "max_possible_score": 10,
            "factors": [{"points": 2, "label": "Elevated phosphorus"}],
        }
        q = _build_retrieval_query(bfi, notes=None)
        self.assertIn("MODERATE FAVORABILITY", q)
        self.assertIn("cleanup", q.lower())
        self.assertIn("phosphorus", q.lower())


class AttachSourcesTests(unittest.TestCase):
    def test_maps_chunk_ids_to_citations(self) -> None:
        evidence = [
            {
                "chunk_id": "abc123",
                "text": "Runoff delivers phosphorus during storms.",
                "retrieval_summary": "Storm runoff increases nutrient loading.",
                "metadata": {"document_title": "Sample hydrology", "section": "Runoff"},
            }
        ]
        suggestions = [
            {
                "title": "Reduce external phosphorus",
                "category": "algae_cleanup",
                "priority": "short_term",
                "actions": ["Target runoff"],
                "rationale": "Reduce regrowth",
                "evidence_chunk_ids": ["abc123"],
                "source_relevance": [{"chunk_id": "abc123", "why_relevant": "Links storms to nutrients."}],
            }
        ]
        out = _attach_sources(suggestions, evidence)
        self.assertEqual(out[0]["category"], "algae_cleanup")
        self.assertEqual(len(out[0]["sources"]), 1)


class FallbackTests(unittest.TestCase):
    def test_fallback_includes_both_categories(self) -> None:
        bundle = {
            "bfi": {"classification": "HIGH FAVORABILITY", "score": 8, "max_possible_score": 10},
            "inputs": {"streamflow_cfs": 100},
        }
        evidence = [
            {
                "chunk_id": "c1",
                "text": "t",
                "retrieval_summary": "Nutrient control reduces blooms.",
                "metadata": {"document_title": "Doc"},
            }
        ]
        payload = _fallback_suggestions(bundle, evidence)
        cats = {s["category"] for s in payload["recovery_suggestions"]}
        self.assertIn("algae_cleanup", cats)
        self.assertIn("consequence_reduction", cats)


class ConditionsFormatTests(unittest.TestCase):
    def test_formats_inputs_and_drivers(self) -> None:
        bundle = {
            "bfi": {"factors": [{"label": "Warm water", "points": 2, "reason": "Above threshold"}]},
            "inputs": {"water_temperature_c": 24.5},
            "inputs_provenance": {},
        }
        rows = _format_current_conditions(bundle)
        kinds = {r["kind"] for r in rows}
        self.assertIn("driver", kinds)
        self.assertIn("input", kinds)


if __name__ == "__main__":
    unittest.main()
