# -*- coding: utf-8 -*-
"""
===================================
Search Algorithm Performance Tests
===================================

Benchmarks the name-to-code resolution engine under load.
"""

import time
import pytest
from src.services.name_to_code_resolver import resolve_name_to_code

class TestSearchPerformance:
    """Benchmark tests for stock search resolution."""

    @pytest.mark.benchmark
    def test_resolve_name_to_code_fast_path_throughput(self):
        """Benchmark the common fast paths without typo/fuzzy fallbacks dominating runtime."""
        inputs = [
            "2330", "8299", "AAPL", "META",
            "台積電", "群聯", "Meta Platforms",
            "aaaaaaa", "1234567",
        ]

        # Warm caches/import paths before timing.
        for s in inputs:
            resolve_name_to_code(s)

        start_time = time.time()
        iterations = 30
        for _ in range(iterations):
            for s in inputs:
                resolve_name_to_code(s)

        duration = time.time() - start_time
        avg_ms = (duration / (iterations * len(inputs))) * 1000

        print(f"\nAverage fast-path resolution time: {avg_ms:.2f}ms")
        assert avg_ms < 20, f"Fast-path resolution too slow: {avg_ms:.2f}ms"

    @pytest.mark.benchmark
    def test_resolve_name_to_code_unsupported_name_budget(self):
        """Unsupported names should fail fast without fuzzy auto-selection."""
        unsupported_inputs = [
            "未知半導體",
            "不存在的支援標的",
        ]

        for s in unsupported_inputs:
            resolve_name_to_code(s)

        start_time = time.time()
        iterations = 10
        for _ in range(iterations):
            for s in unsupported_inputs:
                assert resolve_name_to_code(s) is None

        duration = time.time() - start_time
        avg_ms = (duration / (iterations * len(unsupported_inputs))) * 1000

        print(f"\nAverage unsupported-name resolution time: {avg_ms:.2f}ms")
        assert avg_ms < 100, f"Unsupported-name resolution too slow: {avg_ms:.2f}ms"

    @pytest.mark.benchmark
    def test_unsupported_name_resolution_budget(self):
        """Unsupported names should fail fast without provider lookup."""
        query = "未支援的標的名稱"

        start_time = time.time()
        iterations = 50
        for _ in range(iterations):
            assert resolve_name_to_code(query) is None

        duration = time.time() - start_time
        avg_ms = (duration / iterations) * 1000

        print(f"\nUnsupported-market name resolution avg time: {avg_ms:.2f}ms")
        assert avg_ms < 20, f"Unsupported-market resolution too slow: {avg_ms:.2f}ms"
