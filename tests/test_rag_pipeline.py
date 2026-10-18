"""Unit tests for scientific RAG ingestion pipeline."""

import json
import unittest
from pathlib import Path

from api.services.rag_chunker import chunk_document, word_count
from api.services.rag_document_processor import process_document
from api.services.rag_embeddings import HashEmbedder, ingest_document, save_embedded_chunks, search_chunks
from api.services.rag_metadata_tagger import assign_tags, tag_chunks

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "data" / "rag" / "sources" / "sample_phosphorus_hydrology.txt"
EXAMPLES = REPO / "data" / "rag" / "examples" / "chunk_samples.json"


class TestDocumentProcessor(unittest.TestCase):
    def test_strips_references_section(self) -> None:
        doc = process_document(
            SAMPLE,
            document_title="Nutrient Loading and Cyanobacterial Bloom Dynamics",
            source_type="research_paper",
            authors="Foxwatch Demo",
            year=2020,
            chapter="Phosphorus and Hydrology",
        )
        body = "\n".join(p for s in doc.sections for p in s.paragraphs)
        self.assertIn("Elevated phosphorus concentrations", body)
        self.assertNotIn("Smith, J.", body)
        self.assertNotIn("bibliography entry", body.lower())

    def test_preserves_section_structure(self) -> None:
        doc = process_document(SAMPLE)
        titles = [s.title for s in doc.sections]
        self.assertTrue(any("Phosphorus" in t for t in titles))
        self.assertTrue(any("Hydrology" in t or "Streamflow" in t for t in titles))


class TestChunker(unittest.TestCase):
    def test_semantic_chunks_respect_word_limits(self) -> None:
        doc = process_document(SAMPLE, document_title="Sample Study", year=2020)
        chunks = chunk_document(
            doc,
            target_min_words=120,
            target_max_words=220,
            hard_max_words=280,
            overlap_words=40,
        )
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(chunk.word_count, 280)
            self.assertNotRegex(chunk.text, r"^\.\.\.")
            self.assertIn(" ", chunk.text)

    def test_overlap_carries_context(self) -> None:
        doc = process_document(SAMPLE)
        chunks = chunk_document(
            doc,
            target_min_words=100,
            target_max_words=180,
            hard_max_words=220,
            overlap_words=30,
        )
        self.assertGreaterEqual(len(chunks), 2)
        first_tail = set(w.lower() for w in chunks[0].text.split()[-30:])
        second_head = set(w.lower() for w in chunks[1].text.split()[:60])
        shared = first_tail.intersection(second_head)
        self.assertGreaterEqual(len(shared), 5)


class TestMetadataTagger(unittest.TestCase):
    def test_assigns_environmental_tags(self) -> None:
        text = (
            "Elevated phosphorus from watershed runoff increases cyanobacterial "
            "growth when streamflow is low and precipitation delivers nutrients."
        )
        tags = assign_tags(text)
        self.assertIn("phosphorus", tags)
        self.assertIn("runoff", tags)
        self.assertIn("cyanobacteria", tags)

    def test_retrieval_summary_generated(self) -> None:
        doc = process_document(SAMPLE)
        chunks = chunk_document(doc, target_min_words=80, target_max_words=160, hard_max_words=200)
        tagged = tag_chunks(chunks)
        self.assertTrue(tagged[0].retrieval_summary.startswith("This section explains"))
        self.assertGreater(len(tagged[0].tags), 0)


class TestEmbeddingPipeline(unittest.TestCase):
    def test_end_to_end_ingest_and_search(self) -> None:
        embedder = HashEmbedder(dimensions=128)
        embedded = ingest_document(
            SAMPLE,
            embedder=embedder,
            document_title="Nutrient Loading and Cyanobacterial Bloom Dynamics",
            source_type="research_paper",
            year=2020,
        )
        self.assertGreater(len(embedded), 0)
        for row in embedded:
            self.assertEqual(row.metadata["chunk_id"], row.chunk_id)
            self.assertIn("document_title", row.metadata)
            self.assertEqual(len(row.embedding), 128)

        hits = search_chunks(
            "Why does low streamflow increase bloom favorability?",
            embedded,
            embedder,
            top_k=3,
            min_priority="medium",
        )
        self.assertGreater(len(hits), 0)
        top_text = hits[0][0].text.lower()
        self.assertTrue(
            "streamflow" in top_text or "discharge" in top_text or "hydrolog" in top_text
        )

    def test_write_example_chunk_output(self) -> None:
        """Persist example chunks for manual inspection (metadata + tags + summaries)."""
        embedded = ingest_document(
            SAMPLE,
            embedder=HashEmbedder(dimensions=64),
            document_title="Nutrient Loading and Cyanobacterial Bloom Dynamics",
            source_type="research_paper",
            authors="Demo Authors",
            year=2020,
            chapter="Drivers of Bloom Formation",
        )
        EXAMPLES.parent.mkdir(parents=True, exist_ok=True)
        preview = []
        for row in embedded[:4]:
            preview.append(
                {
                    "chunk_id": row.chunk_id,
                    "document_title": row.metadata["document_title"],
                    "source_type": row.metadata["source_type"],
                    "chapter": row.metadata["chapter"],
                    "section": row.metadata["section"],
                    "authors": row.metadata["authors"],
                    "year": row.metadata["year"],
                    "tags": row.tags,
                    "retrieval_summary": row.retrieval_summary,
                    "retrieval_priority": row.retrieval_priority,
                    "word_count": row.metadata["word_count"],
                    "text_preview": row.text[:280] + ("..." if len(row.text) > 280 else ""),
                }
            )
        EXAMPLES.write_text(json.dumps(preview, indent=2), encoding="utf-8")
        save_embedded_chunks(EXAMPLES.with_name("embedded_chunks.jsonl"), embedded)
        self.assertTrue(EXAMPLES.is_file())


if __name__ == "__main__":
    unittest.main()
