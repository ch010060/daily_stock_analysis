# -*- coding: utf-8 -*-
"""Regression tests for removed chip distribution routing."""

from data_provider.base import DataFetcherManager


class _ChipFetcher:
    def __init__(self, name: str, priority: int, result):
        self.name = name
        self.priority = priority
        self._result = result
        self.calls = 0

    def get_chip_distribution(self, stock_code: str):
        self.calls += 1
        return self._result


def test_manager_chip_distribution_is_removed_and_does_not_call_fetchers():
    fetcher = _ChipFetcher("AkshareFetcher", 1, result=object())
    manager = DataFetcherManager(
        fetchers=[
            fetcher,
        ]
    )

    chip = manager.get_chip_distribution("00981A")

    assert chip is None
    assert fetcher.calls == 0
