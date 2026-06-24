"""Tests for knowledge document status transitions."""

from __future__ import annotations

from app.models.knowledge import DOCUMENT_STATUS_TRANSITIONS, validate_document_transition


class TestDocumentStatusTransitions:
    def test_uploaded_to_scanning(self):
        assert validate_document_transition("uploaded", "scanning")

    def test_uploaded_to_failed(self):
        assert validate_document_transition("uploaded", "failed")

    def test_uploaded_to_deleted(self):
        assert validate_document_transition("uploaded", "deleted")

    def test_scanning_to_parsing(self):
        assert validate_document_transition("scanning", "parsing")

    def test_parsing_to_chunking(self):
        assert validate_document_transition("parsing", "chunking")

    def test_chunking_to_embedding(self):
        assert validate_document_transition("chunking", "embedding")

    def test_embedding_to_ready(self):
        assert validate_document_transition("embedding", "ready")

    def test_ready_to_reindexing(self):
        assert validate_document_transition("ready", "reindexing")

    def test_ready_to_deleted(self):
        assert validate_document_transition("ready", "deleted")

    def test_failed_to_reindexing(self):
        assert validate_document_transition("failed", "reindexing")

    def test_invalid_uploaded_to_ready(self):
        assert not validate_document_transition("uploaded", "ready")

    def test_invalid_deleted_to_any(self):
        for target in DOCUMENT_STATUS_TRANSITIONS:
            assert not validate_document_transition("deleted", target)

    def test_all_states_defined(self):
        expected = {
            "uploaded",
            "scanning",
            "parsing",
            "chunking",
            "embedding",
            "ready",
            "reindexing",
            "failed",
            "deleted",
        }
        assert set(DOCUMENT_STATUS_TRANSITIONS.keys()) == expected
