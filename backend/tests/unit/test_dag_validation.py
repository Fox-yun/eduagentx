"""Tests for DAG validation."""

from __future__ import annotations

import pytest

from app.core.errors import ApiError
from app.models.path import validate_dag


class TestDAGValidation:
    def test_valid_simple_dag(self):
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"source_node_id": "a", "target_node_id": "b"},
            {"source_node_id": "b", "target_node_id": "c"},
        ]
        validate_dag(nodes, edges)  # Should not raise

    def test_valid_diamond_dag(self):
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
        edges = [
            {"source_node_id": "a", "target_node_id": "b"},
            {"source_node_id": "a", "target_node_id": "c"},
            {"source_node_id": "b", "target_node_id": "d"},
            {"source_node_id": "c", "target_node_id": "d"},
        ]
        validate_dag(nodes, edges)  # Should not raise

    def test_empty_nodes_raises(self):
        with pytest.raises(ApiError) as exc_info:
            validate_dag([], [])
        assert exc_info.value.code == "INVALID_DAG"

    def test_duplicate_node_ids_raises(self):
        nodes = [{"id": "a"}, {"id": "a"}]
        with pytest.raises(ApiError) as exc_info:
            validate_dag(nodes, [])
        assert "unique" in exc_info.value.message.lower()

    def test_self_loop_raises(self):
        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"source_node_id": "a", "target_node_id": "a"}]
        with pytest.raises(ApiError) as exc_info:
            validate_dag(nodes, edges)
        assert "self-loop" in exc_info.value.message.lower()

    def test_cycle_raises(self):
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"source_node_id": "a", "target_node_id": "b"},
            {"source_node_id": "b", "target_node_id": "c"},
            {"source_node_id": "c", "target_node_id": "a"},
        ]
        with pytest.raises(ApiError) as exc_info:
            validate_dag(nodes, edges)
        assert "cycle" in exc_info.value.message.lower()

    def test_missing_edge_endpoint_raises(self):
        nodes = [{"id": "a"}]
        edges = [{"source_node_id": "a", "target_node_id": "b"}]
        with pytest.raises(ApiError) as exc_info:
            validate_dag(nodes, edges)
        assert "not found" in exc_info.value.message.lower()

    def test_single_node_valid(self):
        nodes = [{"id": "a"}]
        validate_dag(nodes, [])  # Should not raise

    def test_disconnected_nodes_valid(self):
        nodes = [{"id": "a"}, {"id": "b"}]
        validate_dag(nodes, [])  # Should not raise - both are roots and leaves
